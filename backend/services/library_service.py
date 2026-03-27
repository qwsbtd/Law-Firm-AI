import asyncio
import html
import os
import re
import uuid
from datetime import datetime, timezone, date as date_type

import httpx

from core.config import settings
from core.database import SessionLocal
from models.library_document import LibraryDocument, LibraryDocStatus, DocumentType, LegalCategory

COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v4"


# ── Chunking ─────────────────────────────────────────────────────────────────

def _chunk_library(
    text: str,
    lib_doc_id: int,
    filename: str,
    uploader_id: int,
    title: str,
    document_type: str,
    category: str,
    jurisdiction: str,
    jurisdiction_detail: str,
    citation: str,
    court_name: str,
) -> list[dict]:
    """400-word chunks with 38-word overlap. All metadata values are strings (ChromaDB requirement)."""
    words = text.split()
    chunk_words = 400
    overlap_words = 38
    chunks = []
    start = 0
    chunk_index = 0
    while start < len(words):
        end = min(start + chunk_words, len(words))
        chunk_text_str = " ".join(words[start:end])
        chunks.append(
            {
                "text": chunk_text_str,
                "metadata": {
                    "lib_doc_id":          str(lib_doc_id),
                    "title":               title or "",
                    "filename":            filename or "",
                    "document_type":       document_type or "",
                    "category":            category or "",
                    "jurisdiction":        jurisdiction or "",
                    "jurisdiction_detail": jurisdiction_detail or "",
                    "citation":            citation or "",
                    "court_name":          court_name or "",
                    "chunk_index":         str(chunk_index),
                    "uploader_id":         str(uploader_id),
                },
            }
        )
        chunk_index += 1
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


# ── Background Processing ─────────────────────────────────────────────────────

def process_library_document(
    lib_doc_id: int,
    file_path: str,
    mime_type: str,
    original_filename: str,
    uploader_id: int,
    title: str,
    document_type: str,
    category: str,
    jurisdiction: str,
    jurisdiction_detail: str,
    citation: str,
    court_name: str,
):
    """Background task — creates its own DB session. Must not use request-scoped session."""
    from services.document_service import extract_text
    from services.chroma_service import add_library_chunks
    from services.rag_service import embed_text, summarize_document

    db = SessionLocal()
    try:
        text, page_count = extract_text(file_path, mime_type)
        chunks = _chunk_library(
            text, lib_doc_id, original_filename, uploader_id,
            title, document_type, category,
            jurisdiction, jurisdiction_detail, citation, court_name,
        )
        for chunk in chunks:
            chunk["embedding"] = embed_text(chunk["text"])

        add_library_chunks(lib_doc_id, chunks)
        summary = asyncio.run(summarize_document(text))

        db.query(LibraryDocument).filter(LibraryDocument.id == lib_doc_id).update(
            {
                "status": LibraryDocStatus.ready,
                "summary": summary,
                "page_count": page_count,
                "chunk_count": len(chunks),
                "processed_time": datetime.now(timezone.utc),
                "error_message": None,
            }
        )
        db.commit()
    except Exception as exc:
        db.query(LibraryDocument).filter(LibraryDocument.id == lib_doc_id).update(
            {
                "status": LibraryDocStatus.failed,
                "error_message": str(exc)[:1000],
            }
        )
        db.commit()
    finally:
        db.close()


# ── RAG Query ─────────────────────────────────────────────────────────────────

def _build_where(
    document_type: str | None,
    category: str | None,
    jurisdiction: str | None,
) -> dict | None:
    """Build ChromaDB WHERE filter. Single condition uses bare dict; multiple use $and (required by Chroma)."""
    conditions = []
    if document_type:
        conditions.append({"document_type": {"$eq": document_type}})
    if category:
        conditions.append({"category": {"$eq": category}})
    if jurisdiction:
        conditions.append({"jurisdiction": {"$eq": jurisdiction}})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


async def query_library(
    question: str,
    document_type: str | None = None,
    category: str | None = None,
    jurisdiction: str | None = None,
) -> dict:
    from services.rag_service import embed_text, _get_anthropic_client
    from services.chroma_service import query_library_collection

    q_emb = embed_text(question)
    where = _build_where(document_type, category, jurisdiction)
    results = query_library_collection(q_emb, n_results=5, where=where)

    docs  = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        return {
            "answer": "No relevant library documents found for your question. Try uploading relevant statutes, case law, or past case files.",
            "sources": [],
        }

    context_parts = []
    for i, (doc, meta) in enumerate(zip(docs, metas), 1):
        label = meta.get("citation") or meta.get("title") or meta.get("filename") or f"Source {i}"
        context_parts.append(f"[{label}]\n{doc}")
    context = "\n\n---\n\n".join(context_parts)

    from services.prompts import library_system_prompt
    client = _get_anthropic_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=library_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": f"Library excerpts:\n\n{context}\n\nQuestion: {question}",
            }
        ],
    )

    sources = []
    for meta, dist in zip(metas, dists):
        sources.append(
            {
                "lib_doc_id":    meta.get("lib_doc_id", ""),
                "title":         meta.get("title", ""),
                "filename":      meta.get("filename", ""),
                "document_type": meta.get("document_type", ""),
                "category":      meta.get("category", ""),
                "jurisdiction":  meta.get("jurisdiction", ""),
                "citation":      meta.get("citation", ""),
                "court_name":    meta.get("court_name", ""),
                "chunk_index":   meta.get("chunk_index", ""),
                "score":         round(1 - dist, 4) if dist is not None else None,
            }
        )

    return {"answer": message.content[0].text, "sources": sources}


# ── CourtListener Integration ─────────────────────────────────────────────────

def _strip_html(raw: str) -> str:
    """Minimal HTML stripper using stdlib only (no beautifulsoup4 dependency)."""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _parse_hit(hit: dict) -> dict:
    case_name    = hit.get("caseName") or hit.get("case_name") or f"Cluster {hit.get('cluster_id', '')}"
    citation_raw = hit.get("citation", [])
    citation_str = ", ".join(str(c) for c in citation_raw) if isinstance(citation_raw, list) else str(citation_raw)

    # v4 API: opinion ID and snippet live inside the opinions list
    opinions   = hit.get("opinions") or []
    opinion_id = str(opinions[0]["id"]) if opinions and opinions[0].get("id") else str(hit.get("cluster_id", ""))
    snippet    = ""
    for op in opinions:
        snippet = (op.get("snippet") or "").strip()
        if snippet:
            break

    return {
        "opinion_id": opinion_id,
        "case_name":  case_name,
        "citation":   citation_str,
        "court":      hit.get("court") or hit.get("court_id", ""),
        "date_filed": hit.get("dateFiled") or hit.get("date_filed", ""),
        "url":        f"https://www.courtlistener.com{hit.get('absolute_url', '')}",
        "snippet":    snippet[:300] if snippet else "",
        "status":     hit.get("status", ""),
    }


async def search_courtlistener(query: str, jurisdiction: str = "all") -> list[dict]:
    """Fetch up to 3 pages (≈ 60 results) from CourtListener for broad variety."""
    base_params: dict = {"q": query, "type": "o", "order_by": "score desc"}
    if jurisdiction != "all":
        base_params["court"] = jurisdiction

    seen_ids = set()
    results  = []

    async with httpx.AsyncClient(timeout=20) as client:
        cursor = None
        for _ in range(3):  # up to 3 pages
            params = {**base_params}
            if cursor:
                params["cursor"] = cursor

            resp = await client.get(f"{COURTLISTENER_BASE}/search/", params=params)
            resp.raise_for_status()
            data = resp.json()

            for hit in data.get("results", []):
                opinions   = hit.get("opinions") or []
                opinion_id = str(opinions[0]["id"]) if opinions and opinions[0].get("id") else str(hit.get("cluster_id", ""))
                if opinion_id and opinion_id not in seen_ids:
                    seen_ids.add(opinion_id)
                    results.append(_parse_hit(hit))

            # Follow next-page cursor if present
            next_url = data.get("next")
            if not next_url:
                break
            # Extract cursor from next URL query string
            from urllib.parse import urlparse, parse_qs
            qs     = parse_qs(urlparse(next_url).query)
            cursor = qs.get("cursor", [None])[0]
            if not cursor:
                break

    return results


async def import_courtlistener_opinion(opinion_id: str, uploader_id: int):
    """
    Fetches a CourtListener opinion, saves it to disk, creates a LibraryDocument record.
    Returns (lib_doc_id, file_path, case_name, court_name, citation_str) for the caller
    to schedule background processing.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        meta_resp = await client.get(
            f"{COURTLISTENER_BASE}/opinions/{opinion_id}/",
            headers={"Accept": "application/json"},
        )
        meta_resp.raise_for_status()
        opinion = meta_resp.json()

        # Text extraction — 3-tier fallback
        full_text = (opinion.get("plain_text") or "").strip()

        if not full_text:
            raw_html = (
                opinion.get("html_with_citations")
                or opinion.get("html")
                or ""
            )
            full_text = _strip_html(raw_html)

        if not full_text:
            download_url = opinion.get("download_url", "")
            if download_url:
                dl_resp = await client.get(download_url)
                dl_resp.raise_for_status()
                ct = dl_resp.headers.get("content-type", "")
                full_text = _strip_html(dl_resp.text) if "html" in ct else dl_resp.text

    if not full_text:
        raise ValueError(f"CourtListener opinion {opinion_id} has no retrievable text content")

    # Extract metadata from opinion object
    cluster = opinion.get("cluster") or {}
    if isinstance(cluster, str):
        cluster = {}  # cluster is sometimes a URL — skip secondary fetch

    case_name = (
        cluster.get("case_name")
        or opinion.get("case_name")
        or f"Opinion {opinion_id}"
    )

    citation_list = cluster.get("citations", [])
    citation_str = ", ".join(
        c.get("cite", "") if isinstance(c, dict) else str(c)
        for c in citation_list
    )

    date_filed_str = cluster.get("date_filed") or opinion.get("date_filed", "")
    parsed_date = None
    if date_filed_str:
        try:
            parsed_date = date_type.fromisoformat(date_filed_str[:10])
        except ValueError:
            pass

    court_name = opinion.get("court") or ""

    # Save text to library storage
    os.makedirs(settings.library_path, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}.txt"
    file_path = os.path.join(settings.library_path, stored_filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    file_size = len(full_text.encode("utf-8"))

    # Create DB record
    db = SessionLocal()
    try:
        doc = LibraryDocument(
            title=case_name[:500],
            original_filename=f"{case_name[:100]}.txt",
            filename=stored_filename,
            file_size=file_size,
            mime_type="text/plain",
            status=LibraryDocStatus.processing,
            uploader_id=uploader_id,
            document_type=DocumentType.court_record,
            category=LegalCategory.other,
            jurisdiction="federal",
            jurisdiction_detail=court_name,
            citation=citation_str,
            court_name=court_name,
            case_date=parsed_date,
            courtlistener_id=str(opinion_id),
        )
        db.add(doc)
        db.commit()
        lib_doc_id = doc.id
    finally:
        db.close()

    return lib_doc_id, file_path, case_name, court_name, citation_str
