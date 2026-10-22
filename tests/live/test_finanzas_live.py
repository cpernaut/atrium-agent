"""F-03 against the REAL Supabase (see tests/live/conftest.py).

Checks what only the real database can prove: RLS, constraints, the precarga
and the unique index on rubros. IDs match docs/casos-e2e.md.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from postgrest.exceptions import APIError

from atrium import finanzas
from tests.live.conftest import PREFIX, anon_client

pytestmark = pytest.mark.live


@pytest.fixture
def estructura(users):
    return finanzas.find_rubros(users.a.client, "Estructura")[0]["id"]


def _gasto(obra_id, rubro_id, **cambios):
    fila = {
        "obra_id": obra_id,
        "rubro_id": rubro_id,
        "descripcion": f"{PREFIX} gasto",
        "monto": "1000",
        "moneda": "ARS",
    }
    fila.update(cambios)
    return fila


def test_live_13_anonimo_no_ve_plata(users, obra_de_a, estructura):
    """LIVE-13 (F-03-CA-13): sin login no se ven rubros, gastos ni presupuesto."""

    users.a.client.table("gastos").insert(_gasto(obra_de_a["id"], estructura)).execute()
    anon = anon_client()
    for tabla in ("rubros", "gastos", "presupuesto_items"):
        assert anon.table(tabla).select("id").limit(1).execute().data == [], tabla
    with pytest.raises(APIError):
        anon.table("gastos").insert(_gasto(obra_de_a["id"], estructura)).execute()


def test_live_14_rubros_precargados(users):
    """LIVE-14: los 18 rubros de la precarga existen, incluido Steel frame."""

    nombres = {r["nombre"] for r in finanzas.list_rubros(users.a.client, incluir_inactivos=True)}
    assert {nombre for nombre, _ in finanzas.RUBROS_INICIALES} <= nombres


@pytest.mark.parametrize(
    "cambio",
    [
        {"monto": "0"},
        {"monto": "-5"},
        {"descripcion": "   "},
        {"moneda": "EUR"},
        {"fecha": "FUTURA"},
        {"tipo_cambio": "1200"},  # cotización sin origen
        {"tipo_cambio": "-1", "tipo_cambio_origen": "manual"},
    ],
    ids=["monto0", "monto<0", "sin-descripcion", "moneda", "fecha-futura", "tc-sin-origen", "tc<0"],
)
def test_live_15_la_base_rechaza_gastos_invalidos(users, obra_de_a, estructura, cambio):
    """LIVE-15 (F-03-CA-10): la base rechaza gastos inválidos aunque se saltee la app."""

    if cambio.get("fecha") == "FUTURA":
        cambio = {"fecha": (finanzas.hoy() + timedelta(days=2)).isoformat()}
    with pytest.raises(APIError):
        users.a.client.table("gastos").insert(
            _gasto(obra_de_a["id"], estructura, **cambio)
        ).execute()


def test_live_16_gasto_compartido_anulable_y_no_borrable(users, obra_de_a, estructura):
    """LIVE-16: el gasto de A lo ve B; se anula y se corrige, pero nadie lo borra."""

    gasto, _ = finanzas.add_gasto(
        users.a.client,
        obra_de_a["id"],
        monto="350000",
        moneda="ARS",
        rubro_id=estructura,
        descripcion=f"{PREFIX} Hierro",
        tipo_cambio="1200",  # manual: el test no depende de la fuente de cotizaciones
    )
    assert gasto["creado_por"] == users.a.id
    assert [g["id"] for g in finanzas.list_gastos(users.b.client, obra_de_a["id"])] == [gasto["id"]]

    finanzas.set_tipo_cambio(users.b.client, "gastos", gasto["id"], "1180")
    finanzas.anular_gasto(users.b.client, gasto["id"])
    borrados = users.a.client.table("gastos").delete().eq("id", gasto["id"]).execute().data
    assert borrados == []
    final = finanzas.list_gastos(users.a.client, obra_de_a["id"])[0]
    assert (final["anulado"], final["tipo_cambio_origen"]) == (True, "manual")


def test_live_17_rubros_nuevos_unicos(users, run_id):
    """LIVE-17: el alta de rubros (preparada) funciona y la base no deja duplicarlos."""

    nombre = f"{PREFIX} Rubro {run_id}-{uuid.uuid4().hex[:4]}"
    nuevo = finanzas.create_rubro(users.a.client, nombre)
    assert nuevo["creado_por"] == users.a.id
    with pytest.raises(APIError):  # salteando la app: el índice único lo rechaza
        users.b.client.table("rubros").insert({"nombre": f"  {nombre.upper()} "}).execute()
    assert users.a.client.table("rubros").delete().eq("id", nuevo["id"]).execute().data == []


@pytest.mark.parametrize("nombre", ["Mamposteria", "MAMPOSTERÍA", "  steel   FRAME "])
def test_live_18_rubros_casi_duplicados(users, nombre):
    """LIVE-18: la base rechaza rubros que solo difieren en mayúsculas, tildes o espacios."""

    with pytest.raises(APIError):
        users.a.client.table("rubros").insert({"nombre": nombre}).execute()


@pytest.mark.parametrize(
    "tabla, cambio",
    [
        ("presupuesto_items", {"obra_id": 1}),
        ("presupuesto_items", {"fecha": "2020-01-01"}),
        ("presupuesto_items", {"creado_por": None}),
        ("gastos", {"monto": "1"}),
    ],
    ids=["item-obra", "item-fecha", "item-autor", "gasto-monto"],
)
def test_live_19_columnas_que_no_se_editan(users, obra_de_a, estructura, tabla, cambio):
    """LIVE-19 (F-03-CA-24): salteando la app no se puede mover un ítem de obra ni
    cambiar su fecha o autor, ni el monto de un gasto."""

    if tabla == "gastos":
        fila, _ = finanzas.add_gasto(
            users.a.client,
            obra_de_a["id"],
            monto="10",
            moneda="ARS",
            rubro_id=estructura,
            descripcion=f"{PREFIX} g",
            tipo_cambio="1200",
        )
    else:
        fila, _ = finanzas.add_presupuesto_item(
            users.a.client,
            obra_de_a["id"],
            monto="10",
            moneda="ARS",
            rubro_id=estructura,
            tipo_cambio="1200",
        )
    with pytest.raises(APIError):
        users.a.client.table(tabla).update(cambio).eq("id", fila["id"]).execute()


def test_live_20_editar_y_borrar_item(users, obra_de_a, estructura):
    """LIVE-20 (F-03 R9/R10): B edita el ítem de A; «borrar» lo oculta y lo conserva."""

    item, _ = finanzas.add_presupuesto_item(
        users.a.client,
        obra_de_a["id"],
        monto="10",
        moneda="ARS",
        rubro_id=estructura,
        descripcion=f"{PREFIX} item",
        tipo_cambio="1200",
    )
    editado = finanzas.update_presupuesto_item(
        users.b.client,
        item["id"],
        monto="25",
        moneda="USD",
        rubro_id=estructura,
        descripcion=f"{PREFIX} editado",
        tipo_cambio="1150",
    )
    assert Decimal(str(editado["monto"])) == Decimal("25")
    assert (editado["moneda"], editado["tipo_cambio_origen"]) == ("USD", "manual")
    finanzas.borrar_presupuesto_item(users.b.client, item["id"])
    final = finanzas.get_presupuesto_item(users.a.client, item["id"])
    assert final["anulado"] is True and final["creado_por"] == users.a.id
