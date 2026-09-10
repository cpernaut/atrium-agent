"""Access to the persistent Chroma vector store."""

from __future__ import annotations

from functools import lru_cache

# NB: importing this module first executes atrium/__init__.py, which runs the
# sqlite compatibility shim before chromadb is imported below.
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from atrium.config import settings


@lru_cache(maxsize=1)
def get_vector_store() -> Chroma:
    """Open (or create) the project's Chroma collection. Cached per process."""

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory=str(settings.chroma_dir),
    )


def collection_size() -> int:
    """Number of chunks currently stored."""

    return get_vector_store()._collection.count()
