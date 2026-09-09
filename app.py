"""Streamlit chat UI for the obra assistant.

The graph lives in graph.py and is imported as-is. Run with:

    streamlit run app.py

Needs a `.streamlit/secrets.toml` with:

    APP_PASSWORD = "your-password"
"""

import uuid

import streamlit as st

from graph import build_graph
from ingest import CHROMA_DIR
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
            "Falta APP_PASSWORD en `.streamlit/secrets.toml`. "
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


require_password()

st.title("🏗️ Atrium Agent")
st.caption("Asistente de normativa de obra")

if not CHROMA_DIR.exists():
    st.warning("No se encontró `chroma_db/`. Corré `python ingest.py` primero.")

graph = get_graph()

for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Preguntá sobre normativa de obra…"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Pensando…"):
            result = graph.invoke(
                {"mensajes": [prompt]},
                {"configurable": {"thread_id": st.session_state.thread_id}},
            )
        answer = result["mensajes"][-1]
        st.markdown(answer)

    st.session_state.history.append({"role": "assistant", "content": answer})
