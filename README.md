# Atrium Agent

Asistente de consultas sobre normativa de obra (códigos de edificación
municipales). RAG con LangGraph + Chroma, chat en Streamlit, login e historial
en Supabase.

**App:** https://atrium-agent.streamlit.app

## Arquitectura

```
app.py                  Streamlit UI (solo orquestación y render)
ingest.py               CLI: python ingest.py
atrium/
  config.py             settings + acceso a secrets (sin LangChain/Streamlit)
  sqlite_compat.py      shim de sqlite3 para chromadb en Streamlit Cloud
  vectorstore.py        cliente Chroma (embeddings OpenAI)
  ingestion.py          PDFs de docs/ -> chunks -> Chroma (idempotente)
  rag.py                grafo: classify -> retrieve -> agente_obra
  auth.py               login con Supabase
  persistence.py        historial de chat en la tabla `mensajes`
  observability.py      tracing con LangSmith
tests/                  pytest (sin llamadas a APIs reales)
supabase_schema.sql     tabla `mensajes` + RLS
```

Cada módulo de `atrium/` tiene una sola responsabilidad y las capas de dominio
(`rag`, `ingestion`, `persistence`, `auth`) no importan Streamlit.

## Setup local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # completá OPENAI_API_KEY, SUPABASE_*
python ingest.py               # construye chroma_db/ (ya viene versionado)
streamlit run app.py
```

`streamlit run app.py` también lee `.streamlit/secrets.toml` (ver
`.streamlit/secrets.toml.example`).

## Supabase

1. SQL Editor → correr `supabase_schema.sql` (crea `mensajes` + RLS).
2. Authentication → Users → crear un usuario (la app solo hace login).

## Deploy (Streamlit Community Cloud)

- El repo trae `requirements.txt` con versiones pinneadas y `chroma_db/` ya
  construido, así que no hace falta correr `ingest.py` en el deploy.
- Cargar en **Settings → Secrets**: `OPENAI_API_KEY`, `SUPABASE_URL`,
  `SUPABASE_ANON_KEY` y, opcionalmente, `LANGSMITH_*`.

## Desarrollo

```bash
pytest          # tests
ruff check .    # lint
ruff format .   # formato
```
