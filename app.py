"""Streamlit chat UI for the obra assistant.

The graph lives in graph.py and is imported as-is. Run with:

    streamlit run app.py

Secrets (`.streamlit/secrets.toml` locally, or the app's Secrets on
Streamlit Cloud):

    SUPABASE_URL      = "https://xxxx.supabase.co"
    SUPABASE_ANON_KEY = "..."
    OPENAI_API_KEY    = "sk-..."   # embeddings + chat model

Expects a Supabase table `mensajes` (see supabase_schema.sql) with columns:
    user_id (uuid), thread_id (text), rol (text), contenido (text),
    created_at (timestamptz)
and RLS allowing each user to read/insert their own rows
(`auth.uid() = user_id`). If the table is missing the chat still works,
history just is not persisted.

Optional LangSmith tracing: put the LangSmith snippet in the secrets (any
LANGSMITH_* / LANGCHAIN_* keys, e.g. LANGSMITH_TRACING, LANGSMITH_API_KEY,
LANGSMITH_PROJECT) and they are copied into the environment below, before
the graph is imported.
"""

import sqlite_fix  # noqa: F401  # must precede any chromadb import

import os

import streamlit as st

# Copy every LANGSMITH_* / LANGCHAIN_* secret into the env the LangChain stack
# reads, before graph.py is imported. Optional: with no secrets file, or none
# of these keys, nothing happens.
try:
    _langsmith_keys = [
        k
        for k in st.secrets
        if k.startswith(("LANGSMITH_", "LANGCHAIN_"))
    ]
except Exception:  # noqa: BLE001 - secrets not configured yet
    _langsmith_keys = []
for _key in _langsmith_keys:
    _value = str(st.secrets[_key]).strip()
    # langsmith only treats the exact lowercase string "true" as "on", so a
    # TOML boolean (`true` -> "True") would silently disable tracing.
    if _key.endswith(("TRACING", "TRACING_V2")):
        _value = _value.lower()
    os.environ[_key] = _value

try:  # the langsmith env lookup is lru_cached; drop a stale (pre-secrets) miss
    from langsmith.utils import get_env_var as _ls_get_env_var

    _ls_get_env_var.cache_clear()
except Exception:  # noqa: BLE001
    pass

import uuid
from contextlib import nullcontext
from datetime import datetime, timezone

from supabase import AuthApiError, create_client

from graph import build_graph
from ingest import CHROMA_DIR, COLLECTION_NAME, get_vector_store
from langchain_core.tracers.context import tracing_v2_enabled
from langgraph.checkpoint.memory import MemorySaver

st.set_page_config(page_title="Atrium Agent", page_icon="🏗️")

LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT")
LANGSMITH_ON = bool(
    os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
) and any(
    os.getenv(v, "").lower() == "true"
    for v in (
        "LANGSMITH_TRACING",
        "LANGSMITH_TRACING_V2",
        "LANGCHAIN_TRACING_V2",
        "LANGCHAIN_TRACING",
    )
)


def get_supabase():
    """One Supabase client per browser session (it holds the auth session)."""

    if "supabase" not in st.session_state:
        try:
            url = st.secrets["SUPABASE_URL"]
            anon_key = st.secrets["SUPABASE_ANON_KEY"]
        except (KeyError, FileNotFoundError):
            st.error("Faltan SUPABASE_URL / SUPABASE_ANON_KEY en los secrets.")
            st.stop()
        st.session_state.supabase = create_client(url, anon_key)
    return st.session_state.supabase


def require_login(supabase):
    """Show the login form until the user is authenticated."""

    if st.session_state.get("user"):
        return st.session_state.user

    st.title("🏗️ Atrium Agent")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar")

    if submitted:
        try:
            result = supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except AuthApiError as exc:
            st.error(f"No se pudo iniciar sesión: {exc}")
            st.stop()
        st.session_state.user = result.user
        st.rerun()

    st.stop()


def load_history(supabase, user_id):
    """Past messages for this user, oldest first. [] if persistence is down."""

    try:
        rows = (
            supabase.table("mensajes")
            .select("rol, contenido, created_at")
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
            .data
        )
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort
        st.session_state.persistence_error = str(exc)
        return []
    st.session_state.pop("persistence_error", None)
    return [{"role": row["rol"], "content": row["contenido"]} for row in rows]


def save_exchange(supabase, user_id, thread_id, question, answer):
    """Persist the question and answer as two rows. Best-effort: never raises."""

    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "rol": "user",
            "contenido": question,
            "created_at": now,
        },
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "rol": "assistant",
            "contenido": answer,
            "created_at": now,
        },
    ]
    try:
        supabase.table("mensajes").insert(rows).execute()
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort
        st.session_state.persistence_error = str(exc)
        st.toast("⚠️ No se pudo guardar el historial en Supabase", icon="⚠️")


def _check_langsmith():
    """Hit the LangSmith API with the configured key / endpoint and report."""

    try:
        from langsmith import Client

        client = Client()  # reads LANGSMITH_API_KEY / LANGSMITH_ENDPOINT from env
        list(client.list_projects(limit=1))  # forces an authenticated request
        endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
        st.success(f"Conecta OK ({endpoint})")
        if LANGSMITH_PROJECT and not client.has_project(project_name=LANGSMITH_PROJECT):
            st.warning(
                f"La key funciona pero el proyecto `{LANGSMITH_PROJECT}` no existe "
                "en este workspace todavía (se crea con el primer trace)."
            )
    except Exception as exc:  # noqa: BLE001 - report whatever the API said
        st.error("La API de LangSmith rechazó la conexión:")
        st.exception(exc)


def sidebar(supabase, user):
    with st.sidebar:
        st.write(f"👤 {user.email}")
        if st.button("Cerrar sesión"):
            try:
                supabase.auth.sign_out()
            except Exception:  # noqa: BLE001 - logging out locally regardless
                pass
            st.session_state.clear()
            st.rerun()

        with st.expander("Diagnóstico"):
            key = "OPENAI_API_KEY"
            st.write(("✅ " if os.getenv(key) else "❌ ") + key)

            if LANGSMITH_ON:
                st.write(f"✅ LangSmith → `{LANGSMITH_PROJECT or 'default'}`")
                if st.button("Probar conexión LangSmith"):
                    _check_langsmith()
            else:
                st.write("➖ LangSmith tracing off")

            persistence_error = st.session_state.get("persistence_error")
            if persistence_error:
                st.write("❌ tabla `mensajes` (historial no se guarda)")
                st.caption(persistence_error)
            else:
                st.write("✅ historial (tabla `mensajes`)")

            if not CHROMA_DIR.exists():
                st.write("❌ chroma_db/ no encontrado")
            else:
                try:
                    count = get_vector_store()._collection.count()
                    st.write(f"✅ colección `{COLLECTION_NAME}`: {count} chunks")
                except Exception as exc:  # noqa: BLE001
                    st.write("❌ no se pudo abrir el vector store")
                    st.exception(exc)


supabase = get_supabase()
user = require_login(supabase)

if "graph" not in st.session_state:
    st.session_state.graph = build_graph().compile(checkpointer=MemorySaver())
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.history = load_history(supabase, user.id)

sidebar(supabase, user)

st.title("🏗️ Atrium Agent")
st.caption("Asistente de normativa de obra")

for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("context"):
            with st.expander("📄 Contexto recuperado"):
                st.markdown(message["context"])

if prompt := st.chat_input("Preguntá sobre normativa de obra…"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        run_url = None
        with st.spinner("Pensando…"):
            # Force tracing for this call (and grab a direct link) when
            # LangSmith is configured; otherwise a plain no-op context.
            tracer_ctx = (
                tracing_v2_enabled(project_name=LANGSMITH_PROJECT)
                if LANGSMITH_ON
                else nullcontext()
            )
            try:
                with tracer_ctx as tracer:
                    result = st.session_state.graph.invoke(
                        {"mensajes": [prompt]},
                        {"configurable": {"thread_id": st.session_state.thread_id}},
                    )
                    if tracer is not None:
                        try:
                            run_url = tracer.get_run_url()
                        except Exception:  # noqa: BLE001 - link is best-effort
                            run_url = None
            except Exception as exc:  # noqa: BLE001 - show the error, not a blank reply
                st.exception(exc)
                st.stop()

        answer = result["mensajes"][-1]
        context = result.get("context", "")
        st.markdown(answer)
        with st.expander("📄 Contexto recuperado"):
            st.markdown(context or "_(vacío)_")
        if run_url:
            st.caption(f"[🔎 Ver traza en LangSmith]({run_url})")

    st.session_state.history.append(
        {"role": "assistant", "content": answer, "context": context}
    )
    save_exchange(supabase, user.id, st.session_state.thread_id, prompt, answer)
