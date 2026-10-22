"""Obras tracker data access, against an in-memory fake Supabase."""

import pytest

from atrium import obras
from tests.fake_supabase import FakeSupabase


@pytest.fixture
def db():
    client = FakeSupabase()
    obras.create_obra(client, {"nombre": "Casa Lote 12", "municipio": "La Plata"})
    obras.create_obra(client, {"nombre": "Reforma Quilmes", "municipio": "Quilmes"})
    return client


def test_create_requires_name():
    with pytest.raises(obras.ObrasError):
        obras.create_obra(FakeSupabase(), {"nombre": "  "})


def test_find_by_id_or_partial_name(db):
    assert obras.find_obras(db, "#1")[0]["nombre"] == "Casa Lote 12"
    assert obras.find_obras(db, "lote")[0]["id"] == 1
    assert obras.find_obras(db, "no existe") == []


@pytest.mark.parametrize("avance", [-1, 101, "mucho"])
def test_update_rejects_bad_avance(db, avance):
    with pytest.raises(obras.ObrasError):
        obras.update_obra(db, 1, {"avance": avance})


def test_update_rejects_unknown_estado(db):
    with pytest.raises(obras.ObrasError):
        obras.update_obra(db, 1, {"estado": "Volando"})


def test_update_missing_obra(db):
    with pytest.raises(obras.ObrasError):
        obras.update_obra(db, 99, {"avance": 10})


def test_bitacora_roundtrip(db):
    obras.add_nota(db, 1, "Hormigonado de platea", autor="caro@x.com", fecha="2026-10-20")
    notas = obras.list_bitacora(db, 1)
    assert notas[0]["nota"] == "Hormigonado de platea"
    assert notas[0]["autor"] == "caro@x.com"
    with pytest.raises(obras.ObrasError):
        obras.add_nota(db, 1, "   ")


def test_provider_errors_are_wrapped():
    client = FakeSupabase()
    client.fail = 'relation "obras" does not exist'
    with pytest.raises(obras.ObrasError, match="does not exist"):
        obras.list_obras(client)


def test_normativa_source_by_municipio(db):
    la_plata, quilmes = obras.get_obra(db, 1), obras.get_obra(db, 2)
    assert obras.normativa_source(la_plata) == "Codigo Edificacion de La Plata.pdf"
    assert obras.normativa_source(quilmes) is None
    assert obras.normativa_source(None) is None


def test_normativa_pdfs_exist():
    from atrium.config import settings

    for pdf in obras.NORMATIVA_POR_MUNICIPIO.values():
        assert (settings.docs_dir / pdf).exists(), pdf
