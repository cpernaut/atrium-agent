# Atrium Agent

Asistente de consultas sobre normativa de obra (códigos de edificación
municipales) y tracker de obras del equipo. RAG con LangGraph + Chroma, chat en
Streamlit, login, historial y obras en Supabase.

## Qué hace

- **🤖 Agente** — responde normativa. Si elegís una *obra activa* en la barra
  lateral, busca solo en el código de edificación de su municipio y conoce los
  datos de la obra.
- **Chatear con las obras** — «¿qué obras tengo en curso?», «¿cómo viene Lote
  12?», «anotá que hoy se hormigonó la platea y poné el avance en 40%». El agente
  lee y escribe el tracker con herramientas; solo escribe si se lo pedís.
- **📋 Obras** — listado con avance, alta de obras y bitácora, para todo el
  equipo con el mismo login.

**App:** https://atrium-agent.streamlit.app

## Producto

Visión, glosario, roadmap y fichas de cada funcionalidad con criterios de
aceptación: [`docs/producto/`](docs/producto/README.md). Reglas para trabajar el
código con Claude: [`CLAUDE.md`](CLAUDE.md).

## Arquitectura

```
app.py                  Streamlit UI (solo orquestación y render)
obras_ui.py             pantallas de la sección Obras
ingest.py               CLI: python ingest.py
atrium/
  config.py             settings + acceso a secrets (sin LangChain/Streamlit)
  sqlite_compat.py      shim de sqlite3 para chromadb en Streamlit Cloud
  vectorstore.py        cliente Chroma (embeddings OpenAI)
  ingestion.py          PDFs de docs/ -> chunks -> Chroma (idempotente)
  rag.py                grafo: classify -> retrieve -> agente_obra
  auth.py               login con Supabase
  persistence.py        historial de chat en la tabla `mensajes`
  obras.py              tracker: tablas `obras` y `bitacora`
  obra_tools.py         herramientas del agente para leer/escribir obras
  observability.py      tracing con LangSmith
tests/                  pytest (sin llamadas a APIs reales)
supabase_schema.sql     tablas `mensajes`, `obras`, `bitacora` + RLS
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

1. SQL Editor → correr `supabase_schema.sql` (crea `mensajes`, `obras`,
   `bitacora` + RLS). Se puede volver a correr sin problema.
2. Authentication → Users → crear un usuario por cada persona del equipo (la
   app solo hace login).
3. Authentication → Sign In / Providers → desactivar **Allow new users to sign
   up**: las obras son compartidas por todos los usuarios logueados, así que
   nadie más tiene que poder registrarse.

Para sumar normativa de otro municipio: agregar el PDF a `docs/`, correr
`python ingest.py` y mapear el municipio en `NORMATIVA_POR_MUNICIPIO`
(`atrium/obras.py`).

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
