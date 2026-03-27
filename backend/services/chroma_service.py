import threading
import chromadb
from chromadb.config import Settings as ChromaSettings
from core.config import settings

_client = None
_lock = threading.Lock()


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = chromadb.PersistentClient(
                    path=settings.chroma_persist_path,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
    return _client


def get_or_create_collection(name: str = "documents"):
    return get_chroma_client().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(doc_id: int, chunks: list[dict]):
    """
    chunks: list of {text, embedding, metadata}
    All metadata values must be str/int/float/bool — never None or list.
    """
    collection = get_or_create_collection()
    collection.add(
        ids=[f"{doc_id}_{i}" for i in range(len(chunks))],
        documents=[c["text"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )


def query_collection(
    query_embedding: list[float],
    n_results: int = 5,
    where: dict | None = None,
) -> dict:
    collection = get_or_create_collection()
    kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)


def delete_document_chunks(doc_id: int):
    collection = get_or_create_collection()
    # Fetch IDs first — delete(where=...) is unreliable if key is absent on any doc
    results = collection.get(where={"doc_id": str(doc_id)})
    if results["ids"]:
        collection.delete(ids=results["ids"])


def collection_count() -> int:
    return get_or_create_collection().count()


# ── Law Library helpers — separate "law_library" collection ──────────────────

def get_library_collection():
    """Separate Chroma collection for the Law Library — never mixes with matter documents."""
    return get_or_create_collection("law_library")


def add_library_chunks(lib_doc_id: int, chunks: list[dict]):
    """
    chunks: list of {text, embedding, metadata}
    All metadata values must be str/int/float/bool — never None or list.
    """
    collection = get_library_collection()
    collection.add(
        ids=[f"lib_{lib_doc_id}_{i}" for i in range(len(chunks))],
        documents=[c["text"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )


def query_library_collection(
    query_embedding: list[float],
    n_results: int = 5,
    where: dict | None = None,
) -> dict:
    collection = get_library_collection()
    kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)


def delete_library_chunks(lib_doc_id: int):
    collection = get_library_collection()
    results = collection.get(where={"lib_doc_id": str(lib_doc_id)})
    if results["ids"]:
        collection.delete(ids=results["ids"])


def library_collection_count() -> int:
    return get_library_collection().count()
