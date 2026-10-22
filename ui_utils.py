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


# In Markdown an image always starts with "![". Escaping that "!" (taking care
# of backslashes already in front of it) leaves at most a link, which the
# browser never loads by itself. This holds for nested brackets, reference
# images and any other variant, unlike matching whole image patterns.
_BANG_ANTES_DE_CORCHETE = re.compile(r"(\\*)!(?=\[)")


def respuesta_segura(texto: object) -> str:
    """Agent answers keep their Markdown formatting, but never load images.

    An image in an answer would be fetched by the viewer's browser; a prompt
    injection hidden in stored data could use its URL to leak information.
    """

    def escapar(m: re.Match) -> str:
        barras = m.group(1)
        # Odd number of backslashes: the "!" is already literal.
        return barras + ("!" if len(barras) % 2 else "\\!")

    return _BANG_ANTES_DE_CORCHETE.sub(escapar, str(texto or ""))
