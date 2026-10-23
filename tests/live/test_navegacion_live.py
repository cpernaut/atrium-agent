"""#49 · UX-03 against the REAL Supabase (see tests/live/conftest.py).

What only the real project can prove: the column permissions on ``obras`` and
``rubros``, the «Otros» trigger and the obra activa kept in each user's own
metadata. IDs match docs/casos-e2e.md.
"""

import uuid

import pytest
from postgrest.exceptions import APIError

from atrium import finanzas, obras
from tests.live.conftest import PREFIX, anon_client

pytestmark = pytest.mark.live


def test_live_25_detalle_edita_todos_los_datos(users, obra_de_a):
    """LIVE-25 (UX-03 D4): B edita todos los datos del alta de la obra de A; el
    autor, la fecha de creación y el nombre vacío se rechazan, y sin login no se
    edita nada."""

    cambios = {
        "nombre": f"{PREFIX} Editada {uuid.uuid4().hex[:4]}",
        "cliente": "Pérez",
        "direccion": "Calle 1",
        "municipio": "Berazategui",
        "tipo": "Reforma",
        "estado": "En curso",
        "avance": 15,
        "responsable": "Caro",
        "fecha_inicio": "2026-10-01",
        "fecha_fin_estimada": "2027-03-01",
        "presupuesto": 1000,
        "moneda": "USD",
    }
    fila = obras.update_obra(users.b.client, obra_de_a["id"], dict(cambios))
    assert fila["municipio"] == "Berazategui" and fila["creado_por"] == users.a.id

    for prohibido in ({"creado_por": users.b.id}, {"created_at": "2020-01-01T00:00:00Z"}):
        with pytest.raises(APIError):
            users.b.client.table("obras").update(prohibido).eq("id", obra_de_a["id"]).execute()
    for invalido in ({"nombre": "   "}, {"presupuesto": -1}):
        with pytest.raises(APIError):
            users.b.client.table("obras").update(invalido).eq("id", obra_de_a["id"]).execute()

    anon = anon_client()
    try:
        filas = anon.table("obras").update({"nombre": "x"}).eq("id", obra_de_a["id"]).execute()
        assert not filas.data
    except APIError:
        pass
    assert obras.get_obra(users.a.client, obra_de_a["id"])["nombre"] == cambios["nombre"]


def test_live_26_rubros_ordenar_y_desactivar(users, run_id):
    """LIVE-26 (UX-03-CA-15): un rubro se ordena, se desactiva y se reactiva; el
    nombre no se edita salteando la app y «Otros» no se desactiva."""

    rubro = finanzas.create_rubro(users.a.client, f"{PREFIX} Rubro {run_id}")
    users.b.client.table("rubros").update({"orden": 990}).eq("id", rubro["id"]).execute()
    finanzas.set_rubro_activo(users.b.client, rubro["id"], False)
    finanzas.set_rubro_activo(users.b.client, rubro["id"], True)
    with pytest.raises(APIError):
        users.b.client.table("rubros").update({"nombre": "Otro nombre"}).eq(
            "id", rubro["id"]
        ).execute()

    otros = finanzas.find_rubros(users.a.client, "Otros")[0]
    with pytest.raises(APIError):
        users.a.client.table("rubros").update({"activo": False}).eq("id", otros["id"]).execute()
    assert finanzas.find_rubros(users.a.client, "Otros")[0]["activo"]


def test_live_27_obra_activa_en_la_cuenta_del_usuario(users, obra_de_a):
    """LIVE-27 (UX-03-CA-8): la obra activa queda guardada en la cuenta de quien la
    eligió (se lee al volver a entrar) y no en la de otro usuario."""

    user_a = users.a.client.auth.get_user().user
    obras.guardar_obra_activa(users.a.client, user_a, obra_de_a["id"])

    releida = users.a.client.auth.get_user().user
    assert obras.obra_activa_guardada(releida) == obra_de_a["id"]
    otra = users.b.client.auth.get_user().user
    assert obras.obra_activa_guardada(otra) != obra_de_a["id"]
