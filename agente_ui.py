"""The agent as a floating chat, bottom right, over the Obras screen.

Closed, it is a single «💬 Agente» button; open, a panel with the conversation
and its input. It always works on the obra chosen at the top of the page (one
obra for the whole app, UX-02). History is kept in Supabase (best-effort).

The panel is positioned with CSS on Streamlit's ``st-key-*`` classes: static
styles only, never user content.
"""

from __future__ import annotations

import streamlit as st

from atrium import obras, observability, persistence
from ui_utils import respuesta_segura, texto_seguro

ABIERTO = "agente_abierto"

_CSS = """
<style>
/* The agent floats bottom right, over the page. */
.st-key-agente_flotante {
    position: fixed;
    right: 1.25rem;
    bottom: 1.25rem;
    z-index: 1000;
    width: auto;
    max-width: calc(100vw - 2.5rem);
}
.st-key-agente_abrir button {
    border-radius: 999px;
    padding: 0.6rem 1.2rem;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
}
.st-key-agente_panel {
    width: min(440px, calc(100vw - 2.5rem));
    background: #ffffff;
    border-radius: 12px;
    box-shadow: 0 10px 32px rgba(0, 0, 0, 0.20);
}
/* Title and «Cerrar» on one line, also on phones (Streamlit stacks columns). */
.st-key-agente_cabecera [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; }
.st-key-agente_cabecera [data-testid="stColumn"] { min-width: 0; width: auto; flex: 1 1 auto; }
.st-key-agente_cabecera [data-testid="stColumn"]:last-child { flex: 0 0 auto; }
/* Room at the end of the page, so the button never hides the last content. */
[data-testid="stMainBlockContainer"] { padding-bottom: 6rem; }
/* Phones: the open panel takes the whole width. */
@media (max-width: 640px) {
    .st-key-agente_flotante { right: 0.75rem; bottom: 0.75rem; max-width: calc(100vw - 1.5rem); }
    .st-key-agente_flotante:has(.st-key-agente_panel) { left: 0.75rem; }
    .st-key-agente_panel { width: 100%; }
}
</style>
"""


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
# Floating panel
# --------------------------------------------------------------------------- #
def render_agente(supabase, user, obra: obras.Obra | None) -> None:
    st.html(_CSS)
    with st.container(key="agente_flotante"):
        if not st.session_state.get(ABIERTO):
            if st.button(
                "💬 Agente",
                key="agente_abrir",
                type="primary",
                help="Preguntá normativa o pedile algo sobre la obra elegida.",
            ):
                st.session_state[ABIERTO] = True
                st.rerun()
            return

        with st.container(key="agente_panel", border=True):
            with st.container(key="agente_cabecera"):
                c1, c2 = st.columns([3, 1], vertical_alignment="center")
                c1.markdown("**🤖 Agente**")
                if c2.button("✕ Cerrar", key="agente_cerrar", help="Cerrar el agente"):
                    st.session_state[ABIERTO] = False
                    st.rerun()
            if obra:
                st.caption(f"Trabajando sobre **{texto_seguro(obra['nombre'])}**")
            else:
                st.caption("Sin obra elegida: responde normativa general.")

            mensajes = st.container(height=360, key="agente_mensajes")
            with mensajes:
                if not st.session_state.get("history"):
                    st.caption(
                        "Probá con: «¿qué retiro de frente pide el código?», «anotá que "
                        "llegó el hierro» o «¿cuánto llevamos gastado?»."
                    )
                render_history()
            prompt = st.chat_input("Preguntá o pedí algo…", key="agente_input")
            if prompt:
                with mensajes:
                    handle_prompt(supabase, user, prompt, obra["id"] if obra else None)


def render_history() -> None:
    for message in st.session_state.get("history", []):
        with st.chat_message(message["role"]):
            st.markdown(respuesta_segura(message["content"]))
            for accion in message.get("acciones", []):
                st.caption(texto_seguro(accion))
            if message.get("context"):
                with st.expander("📄 Contexto recuperado"):
                    st.markdown(message["context"])


def handle_prompt(supabase, user, prompt: str, obra_id: int | None) -> None:
    st.session_state.setdefault("history", [])
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        run_url = None
        with st.spinner("Pensando…"):
            try:
                with observability.trace() as tracer:
                    result = st.session_state.graph.invoke(
                        {"mensajes": [prompt], "obra_id": obra_id},
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
        acciones = result.get("acciones") or []
        st.markdown(respuesta_segura(answer))
        for accion in acciones:
            st.caption(texto_seguro(accion))
        with st.expander("📄 Contexto recuperado"):
            st.markdown(context or "_(vacío)_")
        if run_url:
            st.caption(f"[🔎 Ver traza en LangSmith]({run_url})")

    st.session_state.history.append(
        {"role": "assistant", "content": answer, "context": context, "acciones": acciones}
    )
    save_exchange(supabase, user.id, st.session_state.thread_id, prompt, answer)
    if acciones:
        # The agent changed data shown on the page (avance, notes, gastos): reload
        # so the screen behind the chat is up to date. The answer stays in history.
        st.rerun()
