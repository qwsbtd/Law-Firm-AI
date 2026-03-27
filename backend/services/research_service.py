import asyncio
import json
import os
import re
from typing import Optional

import httpx


# ── SearXNG Web Search ────────────────────────────────────────────────────────

async def searxng_search(query: str, max_results: int = 8) -> list[dict]:
    """
    Search the web via self-hosted SearXNG (private, aggregates Google/Bing/DDG/Brave/Presearch).
    Returns empty list gracefully if SearXNG is unreachable.
    """
    base_url = os.getenv("SEARXNG_URL", "http://searxng:8080").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                f"{base_url}/search",
                params={
                    "q":          query,
                    "format":     "json",
                    "categories": "general",
                    "language":   "en",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            {
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "snippet": r.get("content", ""),
                "source":  "searxng",
                "engine":  ", ".join(r.get("engines", [])),
            }
            for r in data.get("results", [])[:max_results]
            if r.get("url")
        ]
    except Exception:
        return []


# ── External Knowledge Source ─────────────────────────────────────────────────

_DETAIL = {
    1: "Provide a concise overview with 3-5 key legal points.",
    2: "Provide a detailed analysis covering main principles, exceptions, and relevant case law standards.",
    3: "Provide an exhaustive legal analysis: doctrine, statutes, landmark cases, circuit splits, and practical implications.",
}


async def _hf_chat(query: str, depth: int, hf_token: str, model: str) -> str:
    """Try HuggingFace Serverless Inference API (requires Pro token for good models)."""
    from huggingface_hub import InferenceClient

    loop   = asyncio.get_event_loop()
    client = InferenceClient(token=hf_token)

    completion = await loop.run_in_executor(
        None,
        lambda: client.chat_completion(
            messages=[
                {
                    "role":    "system",
                    "content": (
                        "You are an authoritative legal knowledge base. Answer legal "
                        "research questions with factual, accurate information based on "
                        "your training. Do not fabricate specific citations."
                    ),
                },
                {"role": "user", "content": f"{_DETAIL[depth]}\n\nLegal question: {query}"},
            ],
            model=model,
            max_tokens=900 + (depth - 1) * 400,
            temperature=0.2,
        ),
    )
    return completion.choices[0].message.content or ""


async def _claude_background_knowledge(query: str, depth: int) -> str:
    """
    Use Claude's own training knowledge as an external knowledge source.
    Always available — no extra API keys needed.
    """
    from services.rag_service import _get_anthropic_client

    client  = _get_anthropic_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800 + (depth - 1) * 400,
        system=(
            "You are an authoritative legal knowledge base. Provide accurate information "
            "about legal principles, statutes, and case law from your training knowledge. "
            "Be thorough and note any important caveats or jurisdictional variations."
        ),
        messages=[
            {"role": "user", "content": f"{_DETAIL[depth]}\n\nLegal research topic: {query}"},
        ],
    )
    return message.content[0].text


async def external_knowledge_search(query: str, depth: int = 1) -> list[dict]:
    """
    Fetch external legal knowledge for the research query.

    Priority:
      1. HuggingFace model (when HF_TOKEN is set — use any chat-capable model)
      2. Claude's built-in knowledge (always available, excellent legal coverage)

    depth=1 → concise; depth=2 → detailed; depth=3 → exhaustive
    """
    hf_token = os.getenv("HF_TOKEN", "").strip()
    model    = os.getenv("HF_RESEARCH_MODEL", "mistralai/Mistral-7B-Instruct-v0.3").strip()

    # Try HuggingFace when a token is explicitly configured
    if hf_token:
        try:
            text        = await _hf_chat(query, depth, hf_token, model)
            model_label = model.split("/")[-1]
            return [
                {
                    "title":   f"HuggingFace LLM: {model_label} (depth {depth})",
                    "url":     f"https://huggingface.co/{model}",
                    "snippet": text.strip(),
                    "source":  "hf_model",
                    "model":   model,
                }
            ]
        except Exception:
            pass  # fall through to Claude

    # Default: Claude background knowledge (no extra API key required)
    try:
        text = await _claude_background_knowledge(query, depth)
        return [
            {
                "title":   f"AI Legal Knowledge — Claude (depth {depth})",
                "url":     "",
                "snippet": text.strip(),
                "source":  "claude_knowledge",
                "model":   "claude-sonnet-4-6",
            }
        ]
    except Exception as exc:
        return [
            {
                "title":   "External knowledge unavailable",
                "url":     "",
                "snippet": str(exc),
                "source":  "knowledge_error",
                "model":   "",
            }
        ]


# ── Internal Document Search ──────────────────────────────────────────────────

async def search_internal_docs(
    question: str,
    matter_id: Optional[int] = None,
    n_results: int = 5,
) -> list[dict]:
    """Search matter documents + law library via ChromaDB."""
    from services.rag_service import embed_text
    from services.chroma_service import query_collection, query_library_collection

    loop = asyncio.get_event_loop()
    q_emb = await loop.run_in_executor(None, embed_text, question)

    results = []

    # Matter documents
    where = {"matter_id": str(matter_id)} if matter_id else None
    matter_raw = query_collection(q_emb, n_results=n_results, where=where)
    for doc, meta, dist in zip(
        matter_raw.get("documents", [[]])[0],
        matter_raw.get("metadatas", [[]])[0],
        matter_raw.get("distances", [[]])[0],
    ):
        results.append({
            "text":   doc,
            "title":  meta.get("title") or meta.get("filename", "Internal Document"),
            "source": "internal_matter",
            "matter": meta.get("matter_number", ""),
            "score":  round(1 - dist, 4) if dist is not None else None,
        })

    # Law Library
    lib_raw = query_library_collection(q_emb, n_results=n_results)
    for doc, meta, dist in zip(
        lib_raw.get("documents", [[]])[0],
        lib_raw.get("metadatas", [[]])[0],
        lib_raw.get("distances", [[]])[0],
    ):
        results.append({
            "text":     doc,
            "title":    meta.get("title") or meta.get("citation") or meta.get("filename", "Library Document"),
            "source":   "library",
            "citation": meta.get("citation", ""),
            "score":    round(1 - dist, 4) if dist is not None else None,
        })

    return results


# ── Context Builder ───────────────────────────────────────────────────────────

def _build_context(hf_results: list[dict], internal_results: list[dict]) -> str:
    return _build_context_full([], hf_results, internal_results)


def _build_context_full(
    web_results: list[dict],
    hf_results: list[dict],
    internal_results: list[dict],
) -> str:
    parts = []

    if internal_results:
        parts.append("=== INTERNAL FIRM DOCUMENTS ===")
        for r in internal_results:
            parts.append(f"[{r['title']}]\n{r['text']}")

    if hf_results:
        parts.append("=== AI LEGAL KNOWLEDGE ===")
        for r in hf_results:
            if r.get("source") not in ("hf_model_error", "knowledge_error"):
                parts.append(f"[{r['title']}]\n{r['snippet']}")

    if web_results:
        parts.append("=== LIVE WEB SEARCH (SearXNG — private, aggregated) ===")
        for r in web_results:
            engines = f" via {r['engine']}" if r.get("engine") else ""
            parts.append(f"[{r['title']}{engines}]\n{r['url']}\n{r['snippet']}")

    return "\n\n---\n\n".join(parts) if parts else "No sources available."


# ── JSON Response Parser ──────────────────────────────────────────────────────

def _parse_json_response(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(cleaned)


# ── Claude Analysis with Confidence Scoring ───────────────────────────────────

async def _ask_with_confidence(
    question: str,
    context: str,
    attempt: int,
) -> dict:
    from services.rag_service import _get_anthropic_client

    client = _get_anthropic_client()

    from services.prompts import research_system_prompt

    retry_note = ""
    if attempt > 1:
        retry_note = (
            f"\n\nNote: This is retry attempt {attempt}. Synthesize all available evidence "
            "to give the most definitive answer possible. Where evidence is limited, reason "
            "from established legal principles and clearly flag any inferences."
        )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=research_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": f"Research sources:\n\n{context}\n\nQuestion: {question}{retry_note}",
            }
        ],
    )

    raw = message.content[0].text
    try:
        parsed = _parse_json_response(raw)
    except Exception:
        parsed = {
            "answer": raw,
            "confidence": 0.5,
            "confidence_reasoning": "Could not parse structured response",
            "key_findings": [],
            "gaps": "",
        }

    return {
        "answer":               parsed.get("answer", raw),
        "confidence":           min(1.0, max(0.0, float(parsed.get("confidence", 0.5)))),
        "confidence_reasoning": parsed.get("confidence_reasoning", ""),
        "key_findings":         parsed.get("key_findings", []),
        "gaps":                 parsed.get("gaps", ""),
    }


# ── Main Research Function ────────────────────────────────────────────────────

async def research_query(
    question: str,
    matter_id: Optional[int] = None,
    confidence_threshold: float = 0.85,
    max_retries: int = 3,
) -> dict:
    """
    Three-source research pipeline:
      1. SearXNG — live private web search (Google/Bing/DDG/Brave/Presearch aggregated)
      2. HuggingFace / Claude — deep legal knowledge
      3. Internal docs — matter files + law library
    Claude synthesizes all sources, scores confidence, retries until threshold met.
    """
    best_result    = None
    attempt_history = []

    for attempt in range(1, max_retries + 1):
        n_results    = 5 + (attempt - 1) * 3
        web_results  = 6 + (attempt - 1) * 2   # 6 → 8 → 10 web results per retry

        # All three sources fetched in parallel
        web_results_data, hf_results, internal_results = await asyncio.gather(
            searxng_search(question, max_results=web_results),
            external_knowledge_search(question, depth=attempt),
            search_internal_docs(question, matter_id, n_results=n_results),
        )

        context = _build_context_full(web_results_data, hf_results, internal_results)

        try:
            result = await _ask_with_confidence(question, context, attempt)
        except Exception as exc:
            result = {
                "answer":               f"Analysis error on attempt {attempt}: {exc}",
                "confidence":           0.0,
                "confidence_reasoning": str(exc),
                "key_findings":         [],
                "gaps":                 "Error during analysis",
            }

        result["web_sources"]      = web_results_data
        result["hf_sources"]       = [r for r in hf_results if r.get("source") not in ("hf_model_error", "knowledge_error")]
        result["internal_sources"] = internal_results

        attempt_history.append({"attempt": attempt, "confidence": result["confidence"]})

        if best_result is None or result["confidence"] > best_result["confidence"]:
            best_result = result

        if result["confidence"] >= confidence_threshold:
            break

    return {
        **best_result,
        "total_attempts":  len(attempt_history),
        "attempt_history": attempt_history,
        "threshold_met":   best_result["confidence"] >= confidence_threshold,
    }
