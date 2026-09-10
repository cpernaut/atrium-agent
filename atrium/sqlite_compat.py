"""Make an old system ``sqlite3`` usable by chromadb.

chromadb requires ``sqlite3 >= 3.35`` and raises at import time otherwise.
Streamlit Community Cloud ships an older one, so we swap in the bundled
``pysqlite3`` build (from ``pysqlite3-binary``, Linux only) before chromadb is
imported. Locally the system ``sqlite3`` is already recent and this is a no-op.
"""

import sqlite3

_MIN_VERSION = (3, 35, 0)

if sqlite3.sqlite_version_info < _MIN_VERSION:
    try:
        import sys

        __import__("pysqlite3")
        sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
    except ModuleNotFoundError:
        # No pysqlite3 wheel here (e.g. macOS dev); fall back to the system one.
        pass
