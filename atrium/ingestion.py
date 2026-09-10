"""Ingest the PDFs in ``docs/`` into the local Chroma vector store.

Idempotent and resumable. Every chunk gets a deterministic id derived from its
content, so each run:

- skips a PDF whose chunk ids are all present already,
- embeds only the missing chunks (e.g. after a run that hit the API quota),
- deletes stale chunks whose text changed.

Running it twice never duplicates documents.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from atrium.config import settings
from atrium.vectorstore import get_vector_store

log = logging.getLogger("atrium.ingestion")

_RETRY_HINT = re.compile(r"(?:retry|try again) in (\d+(?:\.\d+)?)\s*(m?s)")


class QuotaExhausted(RuntimeError):
    """The OpenAI account is out of credit; ingestion cannot continue."""


def _load_pdf_pages(pdf_path: Path) -> list[Document]:
    """One ``Document`` per page that has extractable text."""

    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages: list[Document] = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(
                Document(
                    page_content=text,
                    metadata={"source": pdf_path.name, "page": number},
                )
            )
    return pages


def _chunk_id(chunk: Document, index: int) -> str:
    """Content-derived id: same text -> same id -> no duplicates on re-run."""

    raw = "|".join(
        (
            str(chunk.metadata.get("source")),
            str(chunk.metadata.get("page")),
            str(chunk.metadata.get("start_index")),
            str(index),
            chunk.page_content,
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _retry_delay(message: str, attempt: int) -> float:
    """Prefer the server-suggested delay, else exponential backoff."""

    match = _RETRY_HINT.search(message)
    if match:
        seconds = float(match.group(1)) / (1000 if match.group(2) == "ms" else 1)
        return seconds + 1.0
    return min(60.0, 2.0**attempt)


def _add_with_retry(store: Chroma, batch: list[Document], ids: list[str]) -> None:
    """``add_documents`` retrying the per-minute 429; bail out on no-credit."""

    for attempt in range(1, settings.max_embed_retries + 1):
        try:
            store.add_documents(batch, ids=ids)
            return
        except Exception as exc:  # noqa: BLE001 - provider-specific error types
            message = str(exc)
            if "insufficient_quota" in message or "exceeded your current quota" in message:
                raise QuotaExhausted(
                    "OpenAI account has no credit. What was embedded so far is "
                    "saved; top up and re-run to resume."
                ) from exc
            rate_limited = "429" in message or "rate limit" in message.lower()
            if not rate_limited or attempt == settings.max_embed_retries:
                raise
            delay = _retry_delay(message, attempt)
            log.warning(
                "rate limited, retrying in %.0fs (%d/%d)",
                delay,
                attempt,
                settings.max_embed_retries,
            )
            time.sleep(delay)


def _index_pdf(store: Chroma, pdf_path: Path, splitter: RecursiveCharacterTextSplitter) -> int:
    """Sync one PDF into the store. Returns the number of chunks now indexed."""

    chunks = splitter.split_documents(_load_pdf_pages(pdf_path))
    if not chunks:
        log.info("skip  %s: no extractable text", pdf_path.name)
        return 0

    ids = [_chunk_id(chunk, i) for i, chunk in enumerate(chunks)]
    stored = set(store.get(where={"source": pdf_path.name})["ids"])

    stale = stored - set(ids)
    if stale:
        store.delete(ids=list(stale))

    pending = [i for i, chunk_id in enumerate(ids) if chunk_id not in stored]
    if not pending:
        log.info("skip  %s: already indexed (%d chunks)", pdf_path.name, len(ids))
        return len(ids)

    log.info("index %s: %d of %d chunks pending", pdf_path.name, len(pending), len(chunks))
    for start in range(0, len(pending), settings.embed_batch_size):
        window = pending[start : start + settings.embed_batch_size]
        _add_with_retry(store, [chunks[i] for i in window], [ids[i] for i in window])
        log.info("      %d/%d chunks", start + len(window), len(pending))
    log.info("ok    %s: %d chunks indexed", pdf_path.name, len(ids))
    return len(ids)


def ingest() -> int:
    """Index every ``docs/*.pdf``. Returns the total chunk count."""

    pdf_paths = sorted(settings.docs_dir.glob("*.pdf"))
    if not pdf_paths:
        log.warning("no PDFs found in %s/", settings.docs_dir)
        return 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        add_start_index=True,
    )
    store = get_vector_store()
    total = sum(_index_pdf(store, path, splitter) for path in pdf_paths)
    log.info("done. %d chunks in %s/", total, settings.chroma_dir)
    return total


def main() -> int:
    """CLI entrypoint. Returns a process exit code."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        ingest()
    except QuotaExhausted as exc:
        log.error("%s", exc)
        return 1
    return 0
