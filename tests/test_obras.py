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


def _o(id_, estado):
    return {"id": id_, "nombre": f"O{id_}", "estado": estado}


def test_obra_por_defecto_nunca_es_terminada_si_hay_en_curso():
    """UX-02: newest first, but an En curso obra wins over a newer Terminada."""

    lista = [_o(3, "Terminada"), _o(2, "En curso"), _o(1, "En curso")]
    assert obras.obra_por_defecto(lista) == 2
    assert obras.obra_por_defecto(lista, ultima=1) == 1  # the last one used wins
    assert obras.obra_por_defecto(lista, ultima=99) == 2  # unless it no longer exists


def test_obra_por_defecto_sin_en_curso_y_sin_obras():
    assert obras.obra_por_defecto([_o(3, "Cancelada"), _o(2, "Planificación")]) == 2
    assert obras.obra_por_defecto([_o(3, "Terminada")]) == 3
    assert obras.obra_por_defecto([]) is None


def test_ordenar_para_elegir_mantiene_la_recencia_por_estado():
    lista = [_o(5, "Terminada"), _o(4, "En curso"), _o(3, "Pausada"), _o(2, "En curso")]
    assert [o["id"] for o in obras.ordenar_para_elegir(lista)] == [4, 2, 3, 5]


# --------------------------------------------------------------------------- #
# #49 · Detalle editable y obra activa recordada
# --------------------------------------------------------------------------- #
def test_update_obra_todos_los_datos_del_alta(db):
    cambios = {
        "nombre": "  Casa Lote 12 bis ",
        "cliente": "Pérez",
        "direccion": "Calle 1",
        "municipio": "Berazategui",
        "tipo": "Reforma",
        "estado": "En curso",
        "avance": 20,
        "responsable": "Caro",
        "fecha_inicio": "2026-10-01",
        "fecha_fin_estimada": "2027-03-01",
        "presupuesto": 1000,
        "moneda": "USD",
    }
    assert set(cambios) == set(obras.CAMPOS_EDITABLES_OBRA)
    obra = obras.update_obra(db, 1, dict(cambios))
    assert obra["nombre"] == "Casa Lote 12 bis"  # sin espacios de más
    assert obra["municipio"] == "Berazategui" and obra["moneda"] == "USD"


@pytest.mark.parametrize("campo", ["created_at", "creado_por", "id"])
def test_update_obra_no_edita_autor_ni_fecha(db, campo):
    with pytest.raises(obras.ObrasError, match="no se pueden editar"):
        obras.update_obra(db, 1, {campo: "x"})


@pytest.mark.parametrize("nombre", ["", "   ", None])
def test_update_obra_nombre_obligatorio(db, nombre):
    with pytest.raises(obras.ObrasError, match="necesita un nombre"):
        obras.update_obra(db, 1, {"nombre": nombre})


@pytest.mark.parametrize("presupuesto", [-1, "mucho"])
def test_update_obra_presupuesto_invalido(db, presupuesto):
    with pytest.raises(obras.ObrasError, match="presupuesto"):
        obras.update_obra(db, 1, {"presupuesto": presupuesto})


class _Auth:
    def __init__(self, falla=False):
        self.falla = falla
        self.llamadas = []

    def update_user(self, atributos):
        if self.falla:
            raise RuntimeError("network down")
        self.llamadas.append(atributos)


@pytest.mark.parametrize(
    ("metadata", "esperado"),
    [
        ({"obra_activa": 7}, 7),
        ({"obra_activa": "7"}, 7),
        ({}, None),
        (None, None),
        ({"obra_activa": "abc"}, None),
        ({"obra_activa": -3}, None),
        ({"obra_activa": True}, None),
        ("no es un dict", None),
    ],
)
def test_obra_activa_guardada_es_dato_no_confiable(metadata, esperado):
    from types import SimpleNamespace

    assert obras.obra_activa_guardada(SimpleNamespace(user_metadata=metadata)) == esperado


def test_guardar_obra_activa_en_los_metadatos_del_usuario(db):
    from types import SimpleNamespace

    db.auth = _Auth()
    user = SimpleNamespace(user_metadata={})
    obras.guardar_obra_activa(db, user, 2)
    assert db.auth.llamadas == [{"data": {"obra_activa": 2}}]
    assert obras.obra_activa_guardada(user) == 2


def test_guardar_obra_activa_error_en_espanol(db):
    from types import SimpleNamespace

    db.auth = _Auth(falla=True)
    with pytest.raises(obras.ObrasError, match="No se pudo recordar la obra activa"):
        obras.guardar_obra_activa(db, SimpleNamespace(user_metadata={}), 2)
