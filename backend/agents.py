import operator
from typing import Annotated, TypedDict
from pydantic import BaseModel, Field
from ddgs import DDGS
from langgraph.graph import StateGraph, END
from config import llm, settings
import rag


class State(TypedDict, total=False):
    query: str
    sub_queries: list[str]
    need_web: bool
    need_docs: bool
    evidence: Annotated[list[dict], operator.add]
    web_done: bool
    docs_done: bool
    analysis: str
    report: str
    feedback: str
    approved: bool
    revisions: int
    trace: Annotated[list[str], operator.add]


class Plan(BaseModel):
    sub_queries: list[str] = Field(description="2-4 focused search queries")
    need_web: bool = Field(description="True if external/current web info is needed")
    need_docs: bool = Field(description="True if the user's uploaded documents are relevant")


class Grade(BaseModel):
    relevant: bool
    better_query: str = Field(description="Rewritten query if not relevant, else empty")


class Review(BaseModel):
    approved: bool = Field(description="True only if every claim is supported by cited evidence")
    feedback: str = Field(description="Unsupported claims / citation errors to fix")


def _fmt(evidence: list[dict]) -> str:
    return "\n\n".join(f"[{i+1}] ({e['source']}) {e['content']}" for i, e in enumerate(evidence))


def supervisor(s: State):
    p = llm.with_structured_output(Plan).invoke(
        f"Plan research for: {s['query']}\nUser has uploaded documents: {rag.has_docs()}")
    return {"sub_queries": p.sub_queries, "need_web": p.need_web or not rag.has_docs(),
            "need_docs": p.need_docs and rag.has_docs(), "revisions": 0,
            "trace": [f"supervisor: web={p.need_web} docs={p.need_docs} queries={p.sub_queries}"]}


def route(s: State) -> str:
    if s.get("need_web") and not s.get("web_done"):
        return "researcher"
    if s.get("need_docs") and not s.get("docs_done"):
        return "retriever"
    return "analyst"


def researcher(s: State):
    ev = []
    with DDGS() as d:
        for q in s["sub_queries"]:
            try:
                ev += [{"source": r["href"], "title": r["title"], "content": r["body"]} for r in d.text(q, max_results=3)]
            except Exception as e:
                ev.append({"source": "error", "title": q, "content": f"search failed: {e}"})
    ev = list({e["source"]: e for e in ev if e["source"] != "error"}.values())
    return {"evidence": ev, "web_done": True, "trace": [f"researcher: {len(ev)} web results"]}


def retriever(s: State):
    ev, log = [], []
    for q in s["sub_queries"]:
        docs = rag.search(q, k=3)
        g = llm.with_structured_output(Grade).invoke(
            f"Query: {q}\nDocs:\n{_fmt([{'source': '', 'content': d.page_content[:500]} for d in docs])}\nAre these relevant?")
        if not g.relevant and g.better_query:
            docs = rag.search(g.better_query, k=3)
            log.append(f"rewrote '{q}' -> '{g.better_query}'")
        ev += [{"source": f"{d.metadata.get('source')}" + (f" p.{d.metadata['page']}" if 'page' in d.metadata else ""),
                "title": d.metadata.get("source"), "content": d.page_content} for d in docs]
    return {"evidence": ev, "docs_done": True, "trace": [f"retriever: {len(ev)} chunks {log}"]}


def analyst(s: State):
    r = llm.invoke(f"Question: {s['query']}\nEvidence:\n{_fmt(s['evidence'])}\n\n"
                   "Extract key findings, note agreements/conflicts between sources, and cite evidence as [n].")
    return {"analysis": r.text, "trace": ["analyst: findings extracted"]}


def writer(s: State):
    fix = f"\nReviewer feedback to address:\n{s['feedback']}" if s.get("feedback") else ""
    r = llm.invoke(f"Write a concise markdown research report answering: {s['query']}\n"
                   f"Analysis:\n{s['analysis']}\nEvidence:\n{_fmt(s['evidence'])}\n"
                   f"Every factual claim must cite evidence as [n]. Do not invent sources.{fix}")
    return {"report": r.text, "trace": [f"writer: draft v{s.get('revisions', 0) + 1}"]}


def reviewer(s: State):
    v = llm.with_structured_output(Review).invoke(
        f"Verify each claim in the report against the cited evidence.\nEvidence:\n{_fmt(s['evidence'])}\n\nReport:\n{s['report']}")
    return {"approved": v.approved, "feedback": v.feedback, "revisions": s.get("revisions", 0) + 1,
            "trace": [f"reviewer: approved={v.approved} {v.feedback[:150]}"]}


def after_review(s: State) -> str:
    return END if s["approved"] or s["revisions"] >= settings.max_revisions else "writer"


g = StateGraph(State)
for name, fn in [("supervisor", supervisor), ("researcher", researcher), ("retriever", retriever),
                 ("analyst", analyst), ("writer", writer), ("reviewer", reviewer)]:
    g.add_node(name, fn)
g.set_entry_point("supervisor")
for n in ("supervisor", "researcher", "retriever"):
    g.add_conditional_edges(n, route, ["researcher", "retriever", "analyst"])
g.add_edge("analyst", "writer")
g.add_edge("writer", "reviewer")
g.add_conditional_edges("reviewer", after_review, ["writer", END])
graph = g.compile()


def run(query: str) -> dict:
    return graph.invoke({"query": query, "evidence": [], "trace": []})


def stream(query: str):
    """Yields ("step", text) for each agent step, then ("final", state)."""
    seen, state = 0, {}
    for state in graph.stream({"query": query, "evidence": [], "trace": []}, stream_mode="values"):
        for t in state.get("trace", [])[seen:]:
            yield "step", t
        seen = len(state.get("trace", []))
    yield "final", state
