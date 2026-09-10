"""Streamlit chat UI for the Atrium obra assistant.

Run with ``streamlit run app.py``. All domain logic lives in the ``atrium``
package; this module is only wiring and rendering.

Secrets (``.streamlit/secrets.toml`` locally, or the app's Secrets on
Streamlit Cloud) — see ``.env.example`` for the full list:

    SUPABASE_URL, SUPABASE_ANON_KEY   # login + history
    OPENAI_API_KEY                    # embeddings + chat model
    LANGSMITH_TRACING, LANGSMITH_API_KEY, LANGSMITH_PROJECT   # optional tracing
"""

import streamlit as st

from atrium.config import apply_env

# Bridge secrets into os.environ before importing anything that reads them
# (LangChain / langsmith / OpenAI / Supabase clients).
try:
    _secrets = {key: st.secrets[key] for key in st.secrets}
except Exception:  # noqa: BLE001 - no secrets file configured yet
    _secrets = {}
apply_env(_secrets)

import uuid  # noqa: E402

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from supabase import AuthApiError  # noqa: E402

from atrium import auth, observability, persistence  # noqa: E402
from atrium.config import ConfigError, settings  # noqa: E402
from atrium.rag import build_graph  # noqa: E402
from atrium.vectorstore import collection_size  # noqa: E402

observability.refresh_env_cache()

st.set_page_config(page_title="Atrium Agent", page_icon="🏗️")


# --------------------------------------------------------------------------- #
# Session resources
# --------------------------------------------------------------------------- #
def get_supabase():
    if "supabase" not in st.session_state:
        try:
            st.session_state.supabase = auth.create_supabase()
        except ConfigError as exc:
            st.error(str(exc))
            st.stop()
    return st.session_state.supabase


def get_graph():
    if "graph" not in st.session_state:
        st.session_state.graph = build_graph().compile(checkpointer=MemorySaver())
    return st.session_state.graph


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def require_login(supabase):
    if st.session_state.get("user"):
        return st.session_state.user

    st.title("🏗️ Atrium Agent")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar")

    if submitted:
        try:
            st.session_state.user = auth.sign_in(supabase, email, password)
        except AuthApiError as exc:
            st.error(f"No se pudo iniciar sesión: {exc}")
            st.stop()
        st.rerun()

    st.stop()


# --------------------------------------------------------------------------- #
# History (Supabase-backed, best-effort)
# --------------------------------------------------------------------------- #
def load_history(supabase, user_id) -> list[dict]:
    try:
        messages = persistence.load_history(supabase, user_id)
    except persistence.PersistenceError as exc:
        st.session_state.persistence_error = str(exc)
        return []
    st.session_state.pop("persistence_error", None)
    return [{"role": m.role, "content": m.content} for m in messages]


def save_exchange(supabase, user_id, thread_id, question, answer) -> None:
    try:
        persistence.save_exchange(supabase, user_id, thread_id, question, answer)
    except persistence.PersistenceError as exc:
        st.session_state.persistence_error = str(exc)
        st.toast("⚠️ No se pudo guardar el historial en Supabase", icon="⚠️")


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def render_sidebar(supabase, user) -> None:
    with st.sidebar:
        st.write(f"👤 {user.email}")
        if st.button("Cerrar sesión"):
            auth.sign_out(supabase)
            st.session_state.clear()
            st.rerun()

        with st.expander("Diagnóstico"):
            _diagnostics()


def _diagnostics() -> None:
    st.write(("✅ " if _has_openai_key() else "❌ ") + "OPENAI_API_KEY")

    if observability.tracing_enabled():
        st.write(f"✅ LangSmith → `{observability.tracing_project() or 'default'}`")
        if st.button("Probar conexión LangSmith"):
            ok, message = observability.check_connection()
            (st.success if ok else st.error)(message)
    else:
        st.write("➖ LangSmith tracing off")

    error = st.session_state.get("persistence_error")
    if error:
        st.write("❌ tabla `mensajes` (historial no se guarda)")
        st.caption(error)
    else:
        st.write("✅ historial (tabla `mensajes`)")

    if not settings.chroma_dir.exists():
        st.write("❌ `chroma_db/` no encontrado — corré `python ingest.py`")
        return
    try:
        st.write(f"✅ colección `{settings.collection_name}`: {collection_size()} chunks")
    except Exception as exc:  # noqa: BLE001
        st.write("❌ no se pudo abrir el vector store")
        st.exception(exc)


def _has_openai_key() -> bool:
    try:
        return bool(settings.openai_api_key)
    except ConfigError:
        return False


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
def render_history() -> None:
    for message in st.session_state.history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("context"):
                with st.expander("📄 Contexto recuperado"):
                    st.markdown(message["context"])


def handle_prompt(supabase, user, prompt: str) -> None:
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        run_url = None
        with st.spinner("Pensando…"):
            try:
                with observability.trace() as tracer:
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

    st.session_state.history.append({"role": "assistant", "content": answer, "context": context})
    save_exchange(supabase, user.id, st.session_state.thread_id, prompt, answer)


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
supabase = get_supabase()
user = require_login(supabase)
graph = get_graph()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.history = load_history(supabase, user.id)

render_sidebar(supabase, user)

st.title("🏗️ Atrium Agent")
st.caption("Asistente de normativa de obra")

render_history()

if prompt := st.chat_input("Preguntá sobre normativa de obra…"):
    handle_prompt(supabase, user, prompt)
