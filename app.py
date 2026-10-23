"""Streamlit UI for Atrium: the obras tracker with the agent as a floating chat.

Left menu (#49): the obra activa picker and the screens (Obra activa, Obras,
Nueva obra, Rubros, Proveedores). The obra activa is always shown on top.

Run with ``streamlit run app.py``. All domain logic lives in the ``atrium``
package; this module (and the ``*_ui.py`` screens) is only wiring and rendering.

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

import base64  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from supabase import AuthApiError  # noqa: E402

import navegacion  # noqa: E402
import obras_ui  # noqa: E402
from agente_ui import load_history, render_agente  # noqa: E402
from atrium import auth, observability  # noqa: E402
from atrium.config import ConfigError, settings  # noqa: E402
from atrium.rag import build_graph  # noqa: E402
from atrium.vectorstore import collection_size  # noqa: E402
from proveedores_ui import render_proveedores_page  # noqa: E402
from rubros_ui import render_rubros_page  # noqa: E402

observability.refresh_env_cache()

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "atrium-logo.svg"  # isotipo + «ATRIUM STUDIO», para el login
ISOTIPO_CHICO = str(ASSETS / "atrium-favicon.svg")  # trazo grueso: se lee en tamaños chicos
FAVICON = str(ASSETS / "favicon.png")

NOMBRE_APP = "Atrium Studio"
ETIQUETA_BETA = "Versión beta"

# Wide: the budget table (#45) needs the room; on phones it scrolls sideways.
# The menu starts open on computers and closed on phones (#49 D2: "auto").
st.set_page_config(
    page_title=f"{NOMBRE_APP} · Beta",
    page_icon=FAVICON,
    layout="wide",
    initial_sidebar_state="auto",
)
# Arriba a la izquierda va solo el isotipo: el texto del logo no se lee a ese tamaño.
st.logo(ISOTIPO_CHICO, size="large", icon_image=ISOTIPO_CHICO)


def titulo() -> None:
    """App name with a visible beta label (text, not only color)."""

    st.title(NOMBRE_APP)
    beta()


def beta() -> None:
    st.badge(
        ETIQUETA_BETA,
        icon=":material/science:",
        color="orange",
        help="La app está en prueba: puede cambiar y tener errores. Contanos lo que encuentres.",
    )


def logo_centrado(max_px: int = 220) -> None:
    """Full logo, centered, with alt text. Static asset only (no user content)."""

    datos = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    st.markdown(
        f'<div style="text-align:center;margin:0.5rem 0 1rem">'
        f'<img src="data:image/svg+xml;base64,{datos}" alt="Atrium Studio" '
        f'style="width:60%;max-width:{max_px}px;height:auto"></div>',
        unsafe_allow_html=True,
    )


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


def get_graph(supabase, user):
    if "graph" not in st.session_state:
        graph = build_graph(obras_client=supabase, autor=user.email)
        st.session_state.graph = graph.compile(checkpointer=MemorySaver())
    return st.session_state.graph


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def require_login(supabase):
    if st.session_state.get("user"):
        return st.session_state.user

    logo_centrado()
    titulo()
    st.caption("Ingresá con tu cuenta del equipo.")
    with st.form("login"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Contraseña", type="password", key="login_password")
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
# Sidebar
# --------------------------------------------------------------------------- #
def render_cuenta(supabase, user) -> None:
    """Bottom of the left menu: who is logged in, sign out and diagnostics."""

    with st.sidebar:
        st.divider()
        st.caption(f"👤 {user.email}")
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
# Page
# --------------------------------------------------------------------------- #
supabase = get_supabase()
user = require_login(supabase)
graph = get_graph(supabase, user)

# The history is loaded until it is in the session, and the thread id is set
# last: if a rerun interrupts the load (a tap while it runs, a network error),
# the next run tries again instead of leaving a session without history.
if "history" not in st.session_state:
    st.session_state.history = load_history(supabase, user.id)
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# #49 · Left menu, top to bottom: the obra activa picker, the screens, the account.
lista = obras_ui.load_obras(supabase)
with st.sidebar:
    beta()
    obra_id = obras_ui.select_obra(supabase, user, lista or [])
obra = next((o for o in lista or [] if o["id"] == obra_id), None)
sin_obras = lista == []

pagina = navegacion.construir(
    {
        navegacion.OBRA: lambda: obras_ui.render_obra_page(supabase, user, obra, sin_obras),
        navegacion.OBRAS: lambda: obras_ui.render_lista_page(lista, obra),
        navegacion.NUEVA: lambda: obras_ui.render_nueva_page(supabase, sin_obras),
        navegacion.RUBROS: lambda: render_rubros_page(supabase),
        navegacion.PROVEEDORES: lambda: render_proveedores_page(supabase, user),
    },
    por_defecto=navegacion.OBRA,
)
with st.sidebar:
    navegacion.render_menu()
render_cuenta(supabase, user)

# The obra activa is always visible on top; the agent floats bottom right.
obras_ui.render_encabezado(obra)
obras_ui.mostrar_avisos()
pagina.run()
render_agente(supabase, user, obra)
