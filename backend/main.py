import json, time
from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import rag
from agents import stream
from config import settings

app = FastAPI(title="Yuva AI")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"])


class Query(BaseModel):
    query: str


def _result(s: dict, t: float) -> dict:
    return {"report": s.get("report", ""), "approved": s.get("approved", False), "revisions": s.get("revisions", 0),
            "sources": [{"id": i + 1, "source": e["source"], "title": e["title"]} for i, e in enumerate(s.get("evidence", []))],
            "trace": s.get("trace", []), "latency": round(time.time() - t, 2)}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/documents")
def documents():
    return rag.list_docs()


@app.delete("/documents")
def clear_documents():
    rag.clear()
    return {"cleared": True}


@app.post("/upload")
async def upload(files: list[UploadFile]):
    out = {}
    for f in files:
        try:
            n = rag.ingest(f.filename, await f.read())
            out[f.filename] = {"chunks": n} if n else {"error": "no extractable text (scanned/image PDF?)"}
        except Exception as e:
            out[f.filename] = {"error": str(e)[:200]}
    return out


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True)


@app.post("/research")
def research(q: Query):
    t, final = time.time(), {}
    for kind, data in stream(q.query):
        final = data if kind == "final" else final
    return _result(final, t)


@app.post("/research/stream")
def research_stream(q: Query):
    def gen():
        t = time.time()
        try:
            for kind, data in stream(q.query):
                payload = {"step": data} if kind == "step" else {"final": _result(data, t)}
                yield json.dumps(payload) + "\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")
