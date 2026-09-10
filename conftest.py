# Presence of this file makes pytest add the repo root to sys.path,
# so `import graph` works from tests/.

import os

# Keep test runs out of LangSmith even if .env enables tracing. This runs
# before graph.py's load_dotenv(), which does not override existing vars.
for _var in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING", "LANGSMITH_TRACING", "LANGSMITH_TRACING_V2"):
    os.environ[_var] = "false"
