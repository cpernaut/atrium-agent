"""Live checks against the real Supabase project (see tests/live/conftest.py).

They verify what the simulated suite cannot: the real RLS policies, column
constraints and Auth settings. IDs match docs/casos-e2e.md.
"""

import uuid
from datetime import date

import pytest
from postgrest.exceptions import APIError
from supabase import AuthApiError

from atrium import obras, persistence, propuestas
from atrium.obra_tools import build_obra_tools
from tests.live.conftest import PREFIX, anon_client

pytestmark = pytest.mark.live


# --------------------------------------------------------------------------- #
# Acceso sin login
# --------------------------------------------------------------------------- #
def test_live_01_anonimo_no_ve_obras_ni_bitacora(obra_de_a):
    """LIVE-01: sin login no se lee ninguna obra ni nota (RLS)."""

    anon = anon_client()
    assert anon.table("obras").select("id").eq("id", obra_de_a["id"]).execute().data == []
    assert anon.table("bitacora").select("id").limit(1).execute().data == []
    assert anon.table("mensajes").select("id").limit(1).execute().data == []


def test_live_02_anonimo_no_puede_escribir():
    """LIVE-02: sin login no se puede crear una obra."""

    with pytest.raises(APIError):
        anon_client().table("obras").insert({"nombre": f"{PREFIX} intruso"}).execute()


def test_live_03_registro_publico_desactivado(admin):
    """LIVE-03: nadie puede crearse una cuenta solo (Allow new users to sign up = off)."""

    email = f"e2e-signup-{uuid.uuid4().hex[:8]}@atrium.test"
    try:
        respuesta = anon_client().auth.sign_up({"email": email, "password": uuid.uuid4().hex})
    except AuthApiError:
        return  # esperado: registro desactivado
    if respuesta.user:
        admin.auth.admin.delete_user(respuesta.user.id)
    pytest.fail(
        "El registro público está ACTIVADO: cualquiera puede crearse una cuenta y ver "
        "las obras. Supabase → Authentication → Sign In / Providers → desactivar "
        "«Allow new users to sign up»."
    )


# --------------------------------------------------------------------------- #
# Obras (equipo)
# --------------------------------------------------------------------------- #
def test_live_04_crear_obra_aplica_defaults(users, obra_de_a):
    """LIVE-04: la obra creada queda firmada por su autor y con los valores por defecto."""

    assert obra_de_a["creado_por"] == users.a.id
    assert (obra_de_a["estado"], obra_de_a["moneda"], obra_de_a["avance"]) == (
        "Planificación",
        "ARS",
        0,
    )


def test_live_05_equipo_comparte_obras(users, obra_de_a):
    """LIVE-05: un compañero ve y actualiza la obra de otro (con la capa de la app)."""

    b = users.b.client
    assert obras.get_obra(b, obra_de_a["id"])["nombre"] == obra_de_a["nombre"]
    actualizada = obras.update_obra(b, obra_de_a["id"], {"estado": "En curso", "avance": 25})
    assert (actualizada["estado"], actualizada["avance"]) == ("En curso", 25)
    assert obras.get_obra(users.a.client, obra_de_a["id"])["avance"] == 25


@pytest.mark.parametrize(
    "cambio",
    [{"avance": 150}, {"avance": -1}, {"moneda": "EUR"}],
    ids=["avance>100", "avance<0", "moneda"],
)
def test_live_06_la_base_rechaza_datos_invalidos(users, obra_de_a, cambio):
    """LIVE-06: aun salteando la validación de la app, la base rechaza datos inválidos."""

    with pytest.raises(APIError):
        users.a.client.table("obras").update(cambio).eq("id", obra_de_a["id"]).execute()


def test_live_07_nadie_borra_obras(users, obra_de_a):
    """LIVE-07: ningún usuario puede borrar obras (no hay política de DELETE)."""

    borradas = users.a.client.table("obras").delete().eq("id", obra_de_a["id"]).execute().data
    assert borradas == []
    assert obras.get_obra(users.a.client, obra_de_a["id"]) is not None


# --------------------------------------------------------------------------- #
# Bitácora
# --------------------------------------------------------------------------- #
def test_live_08_bitacora_compartida(users, obra_de_a):
    """LIVE-08: B anota en la obra de A; la fecha toma hoy por defecto y A la ve."""

    obras.add_nota(users.b.client, obra_de_a["id"], "Llegó el hierro", autor=users.b.email)
    nota = obras.list_bitacora(users.a.client, obra_de_a["id"])[0]
    assert (nota["nota"], nota["autor"]) == ("Llegó el hierro", users.b.email)
    assert nota["creado_por"] == users.b.id
    # La fecha por defecto es la del servidor (UTC): puede diferir un día de la local.
    assert abs((date.fromisoformat(nota["fecha"]) - date.today()).days) <= 1


def test_live_09_bitacora_nota_vacia(users, obra_de_a):
    """LIVE-09: la base rechaza una nota sin texto aunque se saltee la app."""

    with pytest.raises(APIError):
        users.a.client.table("bitacora").insert(
            {"obra_id": obra_de_a["id"], "nota": None}
        ).execute()


# --------------------------------------------------------------------------- #
# Historial de chat (privado)
# --------------------------------------------------------------------------- #
def test_live_10_historial_es_privado(users):
    """LIVE-10: cada usuario ve solo su historial; B no lee el de A."""

    persistence.save_exchange(users.a.client, users.a.id, "t-live", "¿Altura?", "9 m")
    propio = persistence.load_history(users.a.client, users.a.id)
    assert [m.content for m in propio][-2:] == ["¿Altura?", "9 m"]
    assert persistence.load_history(users.b.client, users.a.id) == []


def test_live_11_no_se_puede_escribir_historial_ajeno(users):
    """LIVE-11: B no puede guardar mensajes a nombre de A."""

    with pytest.raises(persistence.PersistenceError):
        persistence.save_exchange(users.b.client, users.a.id, "t-live", "x", "y")


# --------------------------------------------------------------------------- #
# Herramientas del agente contra la base real
# --------------------------------------------------------------------------- #
def test_live_12_herramientas_del_agente(users, obra_de_a):
    """LIVE-12: las herramientas del agente leen y proponen; al confirmar se guarda con RLS."""

    pendientes: list[dict] = []
    notas_antes = len(obras.list_bitacora(users.a.client, obra_de_a["id"]))
    tools = {
        t.name: t for t in build_obra_tools(users.a.client, lambda: obra_de_a["id"], pendientes)
    }

    assert obra_de_a["nombre"] in tools["ver_obra"].invoke({})
    tools["agregar_nota_bitacora"].invoke({"nota": "Nota desde el agente"})
    tools["actualizar_obra"].invoke({"avance": 60, "estado": "En curso"})
    rechazo = tools["actualizar_obra"].invoke({"avance": 150})

    assert "entre 0 y 100" in rechazo
    assert len(pendientes) == 2
    assert len(obras.list_bitacora(users.a.client, obra_de_a["id"])) == notas_antes  # sin confirmar
    for p in pendientes:
        propuestas.ejecutar(users.a.client, users.a.email, p)
    assert obras.get_obra(users.a.client, obra_de_a["id"])["avance"] == 60
    assert obras.list_bitacora(users.a.client, obra_de_a["id"])[0]["nota"] == "Nota desde el agente"
