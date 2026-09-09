"""Streamlit chat UI for the obra assistant.

The graph lives in graph.py and is imported as-is. Run with:

    streamlit run app.py

Needs secrets (`.streamlit/secrets.toml` locally, or the app's Secrets on
Streamlit Cloud):

    APP_PASSWORD   = "your-password"
    OPENAI_API_KEY = "sk-..."      # embeddings / retrieval
    GEMINI_API_KEY = "..."         # chat model
"""

import sqlite_fix  # noqa: F401  # must precede any chromadb import

import os
import uuid

import streamlit as st

from graph import build_graph
from ingest import CHROMA_DIR, COLLECTION_NAME, get_vector_store
from langgraph.checkpoint.memory import MemorySaver

st.set_page_config(page_title="Atrium Agent", page_icon="🏗️")


def require_password() -> None:
    """Gate the app behind st.secrets['APP_PASSWORD']."""

    if st.session_state.get("authenticated"):
        return

    try:
        expected = st.secrets["APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        st.error(
            "Falta APP_PASSWORD en los secrets. "
            'Agregá: APP_PASSWORD = "tu-clave"'
        )
        st.stop()

    password = st.text_input("Contraseña", type="password")
    if not password:
        st.stop()
    if password != expected:
        st.error("Contraseña incorrecta.")
        st.stop()

    st.session_state.authenticated = True
    st.rerun()


def get_graph():
    """Compile the graph once per session; reuse it across reruns."""

    if "graph" not in st.session_state:
        st.session_state.graph = build_graph().compile(checkpointer=MemorySaver())
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.history = []
    return st.session_state.graph


def diagnostics() -> None:
    """Sidebar panel to sanity-check the deployment (keys, vector store)."""

    with st.sidebar:
        st.subheader("Diagnóstico")

        for key in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
            ok = bool(os.getenv(key))
            st.write(("✅ " if ok else "❌ ") + key)

        if not CHROMA_DIR.exists():
            st.write("❌ chroma_db/ no encontrado")
            return

        try:
            count = get_vector_store()._collection.count()
            st.write(f"✅ colección `{COLLECTION_NAME}`: {count} chunks")
        except Exception as exc:  # noqa: BLE001 - surface whatever went wrong
            st.write("❌ no se pudo abrir el vector store")
            st.exception(exc)


require_password()

st.title("🏗️ Atrium Agent")
st.caption("Asistente de normativa de obra")

diagnostics()
graph = get_graph()

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
        with st.spinner("Pensando…"):
            try:
                result = graph.invoke(
                    {"mensajes": [prompt]},
                    {"configurable": {"thread_id": st.session_state.thread_id}},
                )
            except Exception as exc:  # noqa: BLE001 - show the error instead of a blank reply
                st.exception(exc)
                st.stop()

        answer = result["mensajes"][-1]
        context = result.get("context", "")
        st.markdown(answer)
        with st.expander("📄 Contexto recuperado"):
            st.markdown(context or "_(vacío)_")

    st.session_state.history.append(
        {"role": "assistant", "content": answer, "context": context}
    )
