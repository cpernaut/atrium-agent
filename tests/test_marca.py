"""Atrium logo: files, login screen and favicon."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SVG = "{http://www.w3.org/2000/svg}"
LOGOS = ("atrium-logo.svg", "atrium-isotipo.svg", "atrium-favicon.svg")


@pytest.mark.parametrize("nombre", LOGOS)
def test_logo_svg_valido_con_titulo(nombre):
    raiz = ET.parse(ASSETS / nombre).getroot()
    assert raiz.tag == f"{SVG}svg"
    titulo = raiz.find(f"{SVG}title")
    assert titulo is not None and titulo.text, "falta <title> para lectores de pantalla"


@pytest.mark.parametrize("nombre", LOGOS)
def test_logo_no_ejecuta_ni_carga_nada(nombre):
    """Sin scripts, contenido HTML embebido ni referencias a archivos externos."""

    for elemento in ET.parse(ASSETS / nombre).getroot().iter():
        etiqueta = elemento.tag.split("}")[-1]
        assert etiqueta not in ("script", "foreignObject", "image", "use"), etiqueta
        for atributo, valor in elemento.attrib.items():
            assert not atributo.lower().startswith("on"), atributo
            if atributo.endswith("href"):
                assert valor.startswith("#"), valor


def test_favicon_cuadrado_y_con_transparencia():
    icono = Image.open(ASSETS / "favicon.png")
    assert icono.size[0] == icono.size[1] >= 128
    assert icono.mode == "RGBA"
