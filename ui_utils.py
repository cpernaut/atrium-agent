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


# ![alt](url) and reference-style images ![alt][ref]
_IMAGEN = re.compile(r"!\[([^\]]*)\]\s*(\([^)]*\)|\[[^\]]*\])")


def respuesta_segura(texto: object) -> str:
    """Agent answers keep their Markdown formatting, but never load images.

    An image in an answer would be fetched by the viewer's browser; a prompt
    injection hidden in stored data could use its URL to leak information.
    Images are shown as plain text instead.
    """

    return _IMAGEN.sub(lambda m: f"[imagen: {m.group(1) or 'sin descripción'}]", str(texto or ""))
