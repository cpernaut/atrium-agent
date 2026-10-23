"""F-06 · Proveedores (#37) against the REAL Supabase (see tests/live/conftest.py).

What only the real project can prove: RLS on the new tables (nothing without
login; each socio writes only their own rating), the unique name and the
trigger that keeps eliminated proveedores out of new gastos. IDs match
docs/casos-e2e.md.
"""

import uuid

import pytest
from postgrest.exceptions import APIError

from atrium import finanzas, proveedores
from tests.live.conftest import PREFIX, anon_client

pytestmark = pytest.mark.live


@pytest.fixture
def proveedor_de_a(users, run_id):
    return proveedores.create_proveedor(
        users.a.client,
        {"nombre": f"{PREFIX} Hierros {run_id}-{uuid.uuid4().hex[:6]}", "telefono": "221 555 1234"},
    )


def test_live_28_proveedores_solo_con_login(users, proveedor_de_a):
    """LIVE-28 (F-06 R5): sin login no se ven proveedores ni calificaciones, y no se
    pueden crear."""

    proveedores.calificar(users.a.client, proveedor_de_a["id"], users.a.id, 5)
    anon = anon_client()
    assert anon.table("proveedores").select("*").execute().data == []
    assert anon.table("proveedor_calificaciones").select("*").execute().data == []
    with pytest.raises(APIError):
        anon.table("proveedores").insert({"nombre": f"{PREFIX} Intruso"}).execute()


def test_live_29_equipo_comparte_la_lista_y_cada_uno_su_calificacion(users, proveedor_de_a):
    """LIVE-29 (F-06 D2): B ve y edita el proveedor de A, no puede repetir su nombre ni
    cambiar, firmar ni atribuirse a nombre de A una calificación; cada uno tiene la suya."""

    assert proveedores.get_proveedor(users.b.client, proveedor_de_a["id"])
    proveedores.update_proveedor(users.b.client, proveedor_de_a["id"], {"zona": "Quilmes"})
    with pytest.raises(APIError):
        users.b.client.table("proveedores").insert(
            {"nombre": proveedor_de_a["nombre"].upper()}
        ).execute()

    mia = proveedores.calificar(users.a.client, proveedor_de_a["id"], users.a.id, 5, "Cumple")
    filas = (
        users.b.client.table("proveedor_calificaciones")
        .update({"estrellas": 1})
        .eq("id", mia["id"])
        .execute()
        .data
    )
    assert filas == []  # RLS: la de A no es de B
    with pytest.raises(APIError):
        users.b.client.table("proveedor_calificaciones").insert(
            {"proveedor_id": proveedor_de_a["id"], "estrellas": 1, "creado_por": users.a.id}
        ).execute()
    falsa = (
        users.b.client.table("proveedor_calificaciones")
        .insert({"proveedor_id": proveedor_de_a["id"], "estrellas": 3, "autor": users.a.email})
        .execute()
        .data[0]
    )
    assert falsa["autor"] == users.b.email  # la base firma con el login, no con lo enviado
    with pytest.raises(APIError):
        users.b.client.table("proveedor_calificaciones").update({"autor": users.a.email}).eq(
            "id", falsa["id"]
        ).execute()
    todas = proveedores.list_calificaciones(users.a.client, proveedor_de_a["id"])
    assert sorted(c["estrellas"] for c in todas) == [3, 5]


def test_live_30_proveedor_eliminado_no_se_elige_en_gastos(users, obra_de_a, proveedor_de_a):
    """LIVE-30 (F-06 R1, R1b): salteando la app, un proveedor eliminado no se elige en
    un gasto ni recibe calificaciones nuevas; el gasto que ya lo tenía lo conserva."""

    estructura = finanzas.find_rubros(users.a.client, "Estructura")[0]["id"]
    item, _ = finanzas.add_presupuesto_item(
        users.a.client,
        obra_de_a["id"],
        monto="10",
        moneda="ARS",
        rubro_id=estructura,
        tipo_cambio="1200",
    )
    gasto, _ = finanzas.add_gasto(
        users.a.client,
        item["id"],
        monto="10",
        moneda="ARS",
        descripcion=f"{PREFIX} g",
        tipo_cambio="1200",
        proveedor_id=proveedor_de_a["id"],
    )
    proveedores.set_archivado(users.a.client, proveedor_de_a["id"], True)
    with pytest.raises(APIError):
        users.a.client.table("gastos").insert(
            {
                "presupuesto_item_id": item["id"],
                "descripcion": f"{PREFIX} otro",
                "monto": "10",
                "moneda": "ARS",
                "proveedor_id": proveedor_de_a["id"],
            }
        ).execute()
    with pytest.raises(APIError):
        users.b.client.table("proveedor_calificaciones").insert(
            {"proveedor_id": proveedor_de_a["id"], "estrellas": 3, "creado_por": users.b.id}
        ).execute()
    users.a.client.table("gastos").update({"monto": "11"}).eq("id", gasto["id"]).execute()
    assert finanzas.get_gasto(users.a.client, gasto["id"])["proveedor_id"] == proveedor_de_a["id"]
