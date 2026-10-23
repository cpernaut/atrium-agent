"""🏢 Proveedores (#49 D3): placeholder until the shared list (#37) is refined."""

from __future__ import annotations

import streamlit as st


def render_proveedores_page() -> None:
    st.header("Proveedores")
    st.info(
        "Próximamente: una lista de proveedores compartida por todas las obras, para "
        "elegirlos al cargar gastos y ofertas. Mientras tanto, el proveedor se escribe "
        "en cada gasto."
    )
