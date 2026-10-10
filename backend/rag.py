import os
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import settings, embeddings

_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


def _load_store() -> InMemoryVectorStore:
    if os.path.exists(settings.store_path):
        return InMemoryVectorStore.load(settings.store_path, embeddings)
    return InMemoryVectorStore(embeddings)


store = _load_store()


def ingest(filename: str, data: bytes) -> int:
    if filename.lower().endswith(".pdf"):
        import io
        pages = PdfReader(io.BytesIO(data)).pages
        docs = [Document(p.extract_text() or "", metadata={"source": filename, "page": i + 1}) for i, p in enumerate(pages)]
    else:
        docs = [Document(data.decode("utf-8", "ignore"), metadata={"source": filename})]
    chunks = [c for c in _splitter.split_documents(docs) if c.page_content.strip()]
    if chunks:
        store.add_documents(chunks)
        os.makedirs(os.path.dirname(settings.store_path), exist_ok=True)
        store.dump(settings.store_path)
    return len(chunks)


def list_docs() -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in store.store.values():
        src = v["metadata"].get("source", "?")
        counts[src] = counts.get(src, 0) + 1
    return counts


def clear():
    store.store.clear()
    if os.path.exists(settings.store_path):
        os.remove(settings.store_path)


def has_docs() -> bool:
    return bool(store.store)


def search(query: str, k: int = 5) -> list[Document]:
    return store.similarity_search(query, k=k) if has_docs() else []
