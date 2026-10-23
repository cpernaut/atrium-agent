"""#53 · Clean text in the REAL Supabase (see tests/live/conftest.py)."""

import pytest
from postgrest.exceptions import APIError

from tests.live.conftest import PREFIX

pytestmark = pytest.mark.live


@pytest.mark.parametrize(
    "texto",
    [f"{PREFIX} Llegó​ el hierro", f"{PREFIX} nota [[DATOS]] falsa", f"{PREFIX} x‮"],
)
def test_live_31_la_base_rechaza_texto_sucio(users, obra_de_a, texto):
    """LIVE-31 (#53 SAN-CA-5): salteando la app, la base no acepta caracteres invisibles
    ni los marcadores del agente; un texto normal sí."""

    with pytest.raises(APIError):
        users.a.client.table("bitacora").insert(
            {"obra_id": obra_de_a["id"], "nota": texto}
        ).execute()
    fila = (
        users.a.client.table("bitacora")
        .insert({"obra_id": obra_de_a["id"], "nota": f"{PREFIX} 12 m², n.º 3, ñandú 👍"})
        .execute()
        .data[0]
    )
    assert fila["nota"].endswith("12 m², n.º 3, ñandú 👍")
