"""The left menu (#49): which screens exist and how to move between them.

Screens are ``st.Page`` objects with fixed ``url_path`` values (so a screen
keeps its link and tests can open it). ``app.py`` builds them on every run with
``construir`` and draws the menu with ``render_menu`` (our own links instead of
Streamlit's automatic menu, so the obra activa picker can go above them); any
screen can send the user elsewhere with ``ir_a``.
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

# url_path of each screen
OBRA = "obra"
OBRAS = "obras"
NUEVA = "nueva-obra"
RUBROS = "rubros"
PROVEEDORES = "proveedores"

ACTUAL = "pagina_actual"  # url_path of the screen on display (session state)

_PAGINAS: dict[str, st.Page] = {}

# Sections of the menu: (title, [(url_path, label, icon)]).
MENU = (
    (
        "Obra",
        (
            (OBRA, "Obra activa", "🏗️"),
            (OBRAS, "Obras", "📋"),
            (NUEVA, "Nueva obra", "➕"),
        ),
    ),
    (
        "Configuración",
        (
            (RUBROS, "Rubros", "🏷️"),
            (PROVEEDORES, "Proveedores", "🏢"),
        ),
    ),
)


def construir(pantallas: dict[str, Callable[[], None]], por_defecto: str) -> st.Page:
    """Register the menu and return the screen to run.

    ``pantallas`` maps each url_path above to the function that draws it;
    ``por_defecto`` is the screen shown when the app opens.
    """

    paginas = []
    for _, opciones in MENU:
        for url, titulo, icono in opciones:
            _PAGINAS[url] = st.Page(
                pantallas[url], title=titulo, icon=icono, url_path=url, default=url == por_defecto
            )
            paginas.append(_PAGINAS[url])
    pagina = st.navigation(paginas, position="hidden")
    st.session_state[ACTUAL] = pagina.url_path or por_defecto
    return pagina


def render_menu() -> None:
    """The screens, by section (call it inside ``st.sidebar``)."""

    for seccion, opciones in MENU:
        st.caption(seccion)
        for url, _, _ in opciones:
            st.page_link(_PAGINAS[url])


def ir_a(url: str) -> None:
    """Open another screen (stops this run, like ``st.rerun``)."""

    st.switch_page(_PAGINAS[url])
