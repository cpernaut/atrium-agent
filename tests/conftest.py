"""Shared test setup."""

import os

# Force LangSmith tracing off for the whole test session, even if a local .env
# enables it. Runs before `atrium` (and its load_dotenv) is imported.
_TRACING_FLAGS = (
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
)
for _flag in _TRACING_FLAGS:
    os.environ[_flag] = "false"
