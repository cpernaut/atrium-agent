"""Atrium Agent — a RAG assistant over Argentine building codes.

Importing the package runs the sqlite compatibility shim first, so any module
that later pulls in ``chromadb`` gets a new-enough ``sqlite3``.
"""

from . import sqlite_compat  # noqa: F401  # side effect: must run before chromadb

__version__ = "0.2.0"
