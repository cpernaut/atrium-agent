"""Make an old system sqlite3 usable by chromadb.

chromadb requires sqlite3 >= 3.35.0 and raises at import time otherwise.
Streamlit Community Cloud ships an older one, so we swap in the bundled
``pysqlite3`` build (from ``pysqlite3-binary``, Linux-only) before chromadb
is imported.

Import this module first, ahead of anything that pulls in chromadb.
"""

import sqlite3

if sqlite3.sqlite_version_info < (3, 35, 0):
    try:
        import sys

        __import__("pysqlite3")
        sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
    except ModuleNotFoundError:
        # No pysqlite3 available (e.g. local dev); the system sqlite3 is used.
        pass
