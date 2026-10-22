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


# Readable report of every run (tests/reporte.py): only writes when
# GITHUB_STEP_SUMMARY or TEST_REPORT_DIR are set, as in the CI workflows.
from tests import reporte  # noqa: E402


def pytest_collection_finish(session):
    reporte.registrar_items(session.items)


def pytest_runtest_logreport(report):
    reporte.registrar_resultado(report)


def pytest_sessionfinish(session, exitstatus):
    reporte.escribir()
