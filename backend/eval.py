"""Compare the multi-agent system vs a single-agent baseline. Usage: python eval.py"""
import json, re, time
from pydantic import BaseModel
from ddgs import DDGS
from config import llm
from agents import run, _fmt

QUESTIONS = [
    {"q": "What is retrieval-augmented generation and why does it reduce hallucination?", "keywords": ["retrieval", "hallucination"]},
    {"q": "Compare LangGraph and CrewAI for multi-agent orchestration.", "keywords": ["langgraph", "crewai"]},
    {"q": "What are the main benefits of the transformer architecture?", "keywords": ["attention", "parallel"]},
]


class Judge(BaseModel):
    supported: int
    total: int


def baseline(q: str) -> dict:
    with DDGS() as d:
        ev = [{"source": r["href"], "title": r["title"], "content": r["body"]} for r in d.text(q, max_results=6)]
    r = llm.invoke(f"Answer with citations [n].\nQuestion: {q}\nEvidence:\n{_fmt(ev)}")
    return {"report": r.text, "evidence": ev}


def score(item: dict, out: dict) -> dict:
    ev, rep = out["evidence"], out["report"]
    cited = {int(n) for g in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", rep) for n in re.split(r"\s*,\s*", g)}
    valid = [n for n in cited if 1 <= n <= len(ev)]
    j = llm.with_structured_output(Judge).invoke(
        f"Count factual claims in the report (total) and how many are supported by their cited evidence (supported).\n"
        f"Evidence:\n{_fmt(ev)}\n\nReport:\n{rep}")
    text = " ".join(e["content"].lower() for e in ev)
    return {"citation_validity": len(valid) / len(cited) if cited else 0,
            "claim_support": j.supported / j.total if j.total else 0,
            "retrieval_recall": sum(k in text for k in item["keywords"]) / len(item["keywords"])}


def main():
    results = {"multi_agent": [], "baseline": []}
    for item in QUESTIONS:
        for name, fn in [("multi_agent", run), ("baseline", baseline)]:
            t = time.time()
            out = fn(item["q"])
            results[name].append({**score(item, out), "latency": time.time() - t})
    summary = {n: {k: round(sum(r[k] for r in rs) / len(rs), 3) for k in rs[0]} for n, rs in results.items()}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
