"""Centralised configuration.

One place holds the tunables (model names, chunking, retrieval depth) and the
access to secrets. Nothing here imports Streamlit or LangChain, so it is cheap
and safe to import from anywhere.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load a local .env once, for `python ingest.py` / tests / notebooks. On
# Streamlit Cloud there is no .env; secrets arrive via the environment instead.
load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
CHROMA_DIR = REPO_ROOT / "chroma_db"

# Env vars whose value is an on/off tracing flag. langsmith only treats the
# exact string "true" as enabled, so these get lowercased on the way in.
TRACING_FLAG_VARS = (
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
)


class ConfigError(RuntimeError):
    """A required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Non-secret configuration with sensible defaults."""

    chat_model: str = "gpt-5-mini"
    embedding_model: str = "text-embedding-3-small"
    retrieval_k: int = 4
    chunk_size: int = 1000
    chunk_overlap: int = 150
    collection_name: str = "obra"
    embed_batch_size: int = 100
    max_embed_retries: int = 5
    docs_dir: Path = DOCS_DIR
    chroma_dir: Path = CHROMA_DIR

    @property
    def openai_api_key(self) -> str:
        return _require_env("OPENAI_API_KEY")

    @property
    def supabase_url(self) -> str:
        return _require_env("SUPABASE_URL")

    @property
    def supabase_anon_key(self) -> str:
        return _require_env("SUPABASE_ANON_KEY")


settings = Settings()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"{name} is not set. Add it to .env locally or to the app's Secrets on Streamlit Cloud."
        )
    return value


def apply_env(values: Mapping[str, Any]) -> None:
    """Copy scalar secrets into ``os.environ`` as strings.

    Used to bridge ``st.secrets`` into the environment that LangChain,
    langsmith and the OpenAI / Supabase clients read. Tracing flags are
    lowercased (a TOML boolean would otherwise arrive as ``"True"``).
    """

    for key, value in values.items():
        if not isinstance(key, str) or isinstance(value, (Mapping, list, tuple)):
            continue
        text = str(value).strip()
        if key in TRACING_FLAG_VARS or key.endswith(("_TRACING", "_TRACING_V2")):
            text = text.lower()
        os.environ[key] = text
