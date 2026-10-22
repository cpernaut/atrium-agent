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


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Mirá ![plano](https://evil.test/a.png?d=secreto)", "Mirá [imagen: plano]"),
        ("![](https://evil.test/a.png)", "[imagen: sin descripción]"),
        ("![x] [ref]", "[imagen: x]"),
        (
            "**Total:** ARS 1.000 y [fuente](https://ok.test)",
            "**Total:** ARS 1.000 y [fuente](https://ok.test)",
        ),
    ],
)
def test_respuesta_segura_bloquea_solo_imagenes(entrada, esperado):
    assert respuesta_segura(entrada) == esperado
