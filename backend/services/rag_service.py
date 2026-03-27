import threading
import anthropic as AnthropicSDK
from llama_index.core import VectorStoreIndex, StorageContext, Settings as LISettings
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from services.chroma_service import get_or_create_collection
from core.config import settings

_index = None
_index_lock = threading.Lock()
_embed_model = None
_embed_lock = threading.Lock()


def get_embed_model() -> HuggingFaceEmbedding:
    global _embed_model
    if _embed_model is None:
        with _embed_lock:
            if _embed_model is None:
                _embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
    return _embed_model


def get_index() -> VectorStoreIndex:
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                collection = get_or_create_collection()
                vector_store = ChromaVectorStore(chroma_collection=collection)
                storage_context = StorageContext.from_defaults(vector_store=vector_store)
                LISettings.embed_model = get_embed_model()
                LISettings.llm = None  # We call Anthropic directly — no LLM through LlamaIndex
                _index = VectorStoreIndex.from_vector_store(
                    vector_store,
                    storage_context=storage_context,
                )
    return _index


def invalidate_index():
    """Call after adding or deleting documents so the index is rebuilt on next access."""
    global _index
    _index = None


def embed_text(text: str) -> list[float]:
    return get_embed_model().get_text_embedding(text)


def _get_anthropic_client() -> AnthropicSDK.Anthropic:
    return AnthropicSDK.Anthropic(api_key=settings.anthropic_api_key)


async def query_rag(
    question: str,
    matter_id: int | None = None,
    doc_id: int | None = None,
) -> dict:
    index = get_index()

    # Build metadata filter
    filters = None
    if doc_id is not None:
        from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
        filters = MetadataFilters(
            filters=[ExactMatchFilter(key="doc_id", value=str(doc_id))]
        )
    elif matter_id is not None:
        from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
        filters = MetadataFilters(
            filters=[ExactMatchFilter(key="matter_id", value=str(matter_id))]
        )

    # Retrieve relevant chunks from matter/doc store
    retriever_kwargs: dict = {"similarity_top_k": 5}
    if filters:
        retriever_kwargs["filters"] = filters
    retriever = index.as_retriever(**retriever_kwargs)
    nodes = retriever.retrieve(question)

    # Also search the Law Library for supplementary context
    from services.chroma_service import query_library_collection
    q_emb = embed_text(question)
    lib_raw     = query_library_collection(q_emb, n_results=3)
    lib_docs    = lib_raw.get("documents", [[]])[0]
    lib_metas   = lib_raw.get("metadatas", [[]])[0]

    context_parts = []

    # Add matter/doc chunks if found
    for i, node in enumerate(nodes, 1):
        fname = node.metadata.get("filename", "unknown")
        context_parts.append(f"[Document: {fname}]\n{node.text}")

    # Add library chunks
    for doc, meta in zip(lib_docs, lib_metas):
        label = meta.get("citation") or meta.get("title") or meta.get("filename", "Library")
        context_parts.append(f"[Law Library: {label}]\n{doc}")

    from services.prompts import chat_system_prompt
    client = _get_anthropic_client()

    if not context_parts:
        user_content = question
    else:
        context      = "\n\n---\n\n".join(context_parts)
        user_content = f"Document excerpts:\n\n{context}\n\nQuestion: {question}"

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=chat_system_prompt(has_documents=bool(context_parts)),
        messages=[{"role": "user", "content": user_content}],
    )

    answer = message.content[0].text

    # Build source list
    sources = []
    for node in nodes:
        sources.append(
            {
                "filename":     node.metadata.get("filename", ""),
                "doc_id":       node.metadata.get("doc_id", ""),
                "matter_number":node.metadata.get("matter_number", ""),
                "chunk_index":  node.metadata.get("chunk_index", ""),
                "score":        round(node.score, 4) if node.score else None,
                "text_preview": node.text[:200],
            }
        )
    for meta in lib_metas:
        sources.append(
            {
                "filename":     meta.get("filename", ""),
                "doc_id":       meta.get("lib_doc_id", ""),
                "matter_number":"library",
                "chunk_index":  meta.get("chunk_index", ""),
                "score":        None,
                "text_preview": meta.get("title", ""),
            }
        )

    return {"answer": answer, "sources": sources}


async def summarize_document(full_text: str) -> str:
    client = _get_anthropic_client()
    # Truncate to 200k chars — well within Claude's context window
    truncated = full_text[:200_000]
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="You are an experienced legal assistant.",
        messages=[
            {
                "role": "user",
                "content": (
                    "Carefully read the following legal document and provide a structured summary including:\n"
                    "1. Document type and purpose\n"
                    "2. Key parties involved\n"
                    "3. Important dates and deadlines\n"
                    "4. Core obligations and rights\n"
                    "5. Notable risk clauses, penalties, or termination conditions\n"
                    "6. Any unusual or notable provisions\n\n"
                    f"Document:\n{truncated}"
                ),
            }
        ],
    )
    return message.content[0].text


def prewarm():
    """Download and cache the embedding model at startup (avoids first-request delay)."""
    get_embed_model()
