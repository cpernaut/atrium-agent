"""CLI entrypoint for the ingestion pipeline: ``python ingest.py``.

The implementation lives in ``atrium.ingestion``.
"""

from atrium.ingestion import main

if __name__ == "__main__":
    raise SystemExit(main())
