"""Ingest the PDFs in docs/ into a local Chroma vector store.

Run:

    python ingest.py

Idempotent and resumable. Every chunk gets a deterministic id derived from its
content, so on each run the script:

- skips a PDF whose chunk ids are all already in the store,
- embeds only the chunks that are missing (e.g. after a partial run that hit
  the API quota), and
- deletes stale chunks whose text changed.

Running it twice never duplicates documents.
"""

import hashlib
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

load_dotenv()

ROOT_DIR = Path(__file__).parent
DOCS_DIR = ROOT_DIR / "docs"
CHROMA_DIR = ROOT_DIR / "chroma_db"
COLLECTION_NAME = "obra"
# Embeddings run on OpenAI (OPENAI_API_KEY). The Gemini free-tier embedding
# quota was too small for these documents; the chat model stays on Gemini.
EMBEDDING_MODEL = "text-embedding-3-small"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Chunks per embedding request (Gemini caps a batch at 100), plus retry
# settings for the per-minute rate limit.
EMBED_BATCH_SIZE = 100
MAX_RETRIES = 5


def get_vector_store() -> Chroma:
    """Open (or create) the persistent Chroma collection used by this project."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Set it in a local .env file.")
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=api_key)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )


def _load_pdf_pages(pdf_path: Path) -> list[Document]:
    """One Document per page that has extractable text."""

    reader = PdfReader(str(pdf_path))
    pages: list[Document] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(
                Document(
                    page_content=text,
                    metadata={"source": pdf_path.name, "page": page_number},
                )
            )
    return pages


def _chunk_id(chunk: Document, index: int) -> str:
    """Content-derived id: same text -> same id -> no duplicates on re-run."""

    raw = "|".join(
        [
            str(chunk.metadata.get("source")),
            str(chunk.metadata.get("page")),
            str(chunk.metadata.get("start_index")),
            str(index),
            chunk.page_content,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _retry_delay(message: str, attempt: int) -> float:
    """Prefer the server-suggested delay, otherwise exponential backoff."""

    match = re.search(r"(?:retry|try again) in (\d+(?:\.\d+)?)\s*(m?s)", message)
    if match:
        seconds = float(match.group(1)) / (1000 if match.group(2) == "ms" else 1)
        return seconds + 1.0
    return min(60.0, 2.0**attempt)


def _add_with_retry(store: Chroma, batch: list[Document], batch_ids: list[str]) -> None:
    """add_documents, retrying on rate limits; bail out if the account is out of credit."""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            store.add_documents(batch, ids=batch_ids)
            return
        except Exception as exc:  # noqa: BLE001 - provider raises its own error types
            message = str(exc)
            if "insufficient_quota" in message or "exceeded your current quota" in message:
                raise SystemExit(
                    "\nThe OpenAI account has no available credit "
                    "(insufficient_quota). What was embedded so far is saved; "
                    "top up the account and re-run `python ingest.py` to resume."
                ) from exc
            rate_limited = "429" in message or "rate limit" in message.lower()
            if not rate_limited or attempt == MAX_RETRIES:
                raise
            delay = _retry_delay(message, attempt)
            print(
                f"      rate limited, retrying in {delay:.0f}s "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )
            time.sleep(delay)


def _index_chunks(store: Chroma, chunks: list[Document], ids: list[str]) -> None:
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        batch_ids = ids[start : start + EMBED_BATCH_SIZE]
        _add_with_retry(store, batch, batch_ids)
        print(f"      {min(start + EMBED_BATCH_SIZE, len(chunks))}/{len(chunks)} chunks")


def ingest() -> None:
    pdf_paths = sorted(DOCS_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {DOCS_DIR}/")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
    )
    store = get_vector_store()

    for pdf_path in pdf_paths:
        pages = _load_pdf_pages(pdf_path)
        chunks = splitter.split_documents(pages)
        if not chunks:
            print(f"skip  {pdf_path.name}: no extractable text")
            continue

        ids = [_chunk_id(chunk, i) for i, chunk in enumerate(chunks)]
        wanted = set(ids)
        stored = set(store.get(where={"source": pdf_path.name})["ids"])

        stale = stored - wanted
        if stale:
            store.delete(ids=list(stale))

        pending = [i for i, chunk_id in enumerate(ids) if chunk_id not in stored]
        if not pending:
            print(f"skip  {pdf_path.name}: already indexed ({len(ids)} chunks)")
            continue

        print(
            f"index {pdf_path.name}: {len(pending)} of {len(chunks)} chunks pending"
        )
        _index_chunks(store, [chunks[i] for i in pending], [ids[i] for i in pending])
        print(f"ok    {pdf_path.name}: {len(ids)} chunks indexed")

    print(f"done. vector store at {CHROMA_DIR}/")


if __name__ == "__main__":
    ingest()
