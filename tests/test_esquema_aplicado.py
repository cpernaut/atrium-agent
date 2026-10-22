"""The «Esquema aplicado» auto-merge check (.github/scripts/esquema_aplicado.py)."""

import importlib.util
from pathlib import Path

import pytest

_RUTA = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "esquema_aplicado.py"
_spec = importlib.util.spec_from_file_location("esquema_aplicado", _RUTA)
esquema_aplicado = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(esquema_aplicado)
decidir = esquema_aplicado.decidir

A, B = "a" * 40, "b" * 40


@pytest.mark.parametrize(
    "cambia, etiqueta, recien, confirmado, actual, esperado",
    [
        (False, False, False, None, A, (True, "")),  # no toca el esquema: pasa
        (True, False, False, None, A, (False, "")),  # cambia el esquema: espera la etiqueta
        (True, True, True, None, A, (True, "registrar")),  # se etiqueta: registra la huella
        (True, True, False, A, A, (True, "")),  # misma huella: pasa
        (True, True, False, A, B, (False, "quitar")),  # commit nuevo o force-push: se invalida
        (True, True, False, None, A, (False, "quitar")),  # etiqueta sin huella registrada
        (True, True, False, A, None, (False, "quitar")),  # no se pudo leer el esquema
    ],
)
def test_decidir(cambia, etiqueta, recien, confirmado, actual, esperado):
    """AUTO-MERGE-1: la etiqueta «esquema aplicado» vale solo para el esquema que se confirmó."""

    assert decidir(cambia, etiqueta, recien, confirmado, actual) == esperado


def test_otra_etiqueta_despues_de_un_cambio_no_aprueba():
    """AUTO-MERGE-2: agregar otra etiqueta después de cambiar el esquema no lo aprueba."""

    # Evento «labeled» de otra etiqueta: no es «recién etiquetado» con esquema aplicado.
    assert decidir(True, True, False, A, B) == (False, "quitar")


def test_todos_los_resultados_tienen_mensaje():
    for clave in [(True, ""), (True, "registrar"), (False, ""), (False, "quitar")]:
        assert esquema_aplicado.MENSAJES[clave]
