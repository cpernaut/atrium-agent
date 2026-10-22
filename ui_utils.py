"""Small helpers shared by the Streamlit screens."""

from __future__ import annotations

import re

# Markdown and Streamlit directives (:color[...], :material/...:, $latex$).
_ESPECIALES = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$:])")


def texto_seguro(valor: object) -> str:
    """User-entered text, safe to put inside ``st.markdown``.

    Escapes Markdown so a description can't render links, images (which would
    load an external URL), headings or Streamlit directives. Newlines are kept
    as Markdown line breaks.
    """

    texto = _ESPECIALES.sub(r"\\\1", str(valor or ""))
    return "  \n".join(texto.splitlines())
