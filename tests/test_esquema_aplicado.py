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
        (True, True, False, A, A, (True, "")),  # misma huella: pasa
        (True, True, False, A, B, (False, "quitar")),  # commit nuevo o force-push: se invalida
        (True, True, False, None, A, (False, "")),  # etiqueta aún sin registrar: espera
        (True, True, False, A, None, (False, "quitar")),  # no se pudo leer el esquema
    ],
)
def test_decidir(cambia, etiqueta, recien, confirmado, actual, esperado):
    """AUTO-MERGE-1: la etiqueta «esquema aplicado» vale solo para el esquema que se confirmó."""

    assert decidir(cambia, etiqueta, recien, confirmado, actual, etiquetado=actual) == esperado


def test_etiquetar_registra_el_esquema_del_commit_etiquetado():
    """AUTO-MERGE-3: al etiquetar se confirma el esquema del commit que tenía el PR."""

    assert decidir(True, True, True, None, A, etiquetado=A) == (True, "registrar")


def test_etiqueta_en_a_y_push_de_b_antes_de_correr_no_aprueba():
    """AUTO-MERGE-4: si llega un push con otro esquema antes de que corra el check de la
    etiqueta, no se confirma el esquema nuevo."""

    assert decidir(True, True, True, None, B, etiquetado=A) == (False, "quitar")


@pytest.mark.parametrize("recien", [True, False])
def test_esquema_ilegible_o_borrado_nunca_aprueba(recien):
    """AUTO-MERGE-5: si no se puede leer el esquema (error de la API o archivo borrado),
    el check falla, también justo al etiquetar."""

    assert decidir(True, True, recien, A, None, etiquetado=None) == (False, "quitar")
    assert decidir(True, True, True, None, A, etiquetado=None) == (False, "quitar")


def test_otra_etiqueta_despues_de_un_cambio_no_aprueba():
    """AUTO-MERGE-2: agregar otra etiqueta después de cambiar el esquema no lo aprueba."""

    # Evento «labeled» de otra etiqueta: no es «recién etiquetado» con esquema aplicado.
    assert decidir(True, True, False, A, B) == (False, "quitar")


def test_todos_los_resultados_tienen_mensaje():
    for clave in [(True, ""), (True, "registrar"), (False, ""), (False, "quitar")]:
        assert esquema_aplicado.MENSAJES[clave]


def test_synchronize_antes_que_labeled_no_quita_la_etiqueta():
    """AUTO-MERGE-6: si la corrida del push llega antes que la de la etiqueta, espera
    sin quitarla; después la de la etiqueta la registra y aprueba."""

    assert decidir(True, True, False, None, A, etiquetado=None) == (False, "")
    assert decidir(True, True, True, None, A, etiquetado=A) == (True, "registrar")


@pytest.mark.parametrize(
    "archivos, esperado",
    [
        ([{"filename": "app.py"}], False),
        ([{"filename": "supabase_schema.sql"}], True),
        ([{"filename": "db/esquema.sql", "previous_filename": "supabase_schema.sql"}], True),
        ([{"filename": "supabase_schema.sql", "previous_filename": "viejo.sql"}], True),
    ],
)
def test_toca_esquema_incluye_renombres(archivos, esperado):
    """AUTO-MERGE-7: renombrar o mover el esquema también cuenta como cambiarlo."""

    assert esquema_aplicado.toca_esquema(archivos) is esperado
