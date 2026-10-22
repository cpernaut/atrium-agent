"""Dólar MEP quotes: parsing, fallback to the previous business day, failures."""

from datetime import date
from decimal import Decimal

import pytest

from atrium import cotizaciones

VIERNES, SABADO, LUNES = date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 19)


@pytest.fixture
def fuente(monkeypatch):
    """Replace the network call; returns the list the fake 'API' serves."""

    cotizaciones.clear_cache()
    datos = {"payload": [], "llamadas": 0, "error": None}

    def fake_fetch():
        datos["llamadas"] += 1
        if datos["error"]:
            raise cotizaciones.CotizacionError(datos["error"])
        return datos["payload"]

    monkeypatch.setattr(cotizaciones, "_fetch_json", fake_fetch)
    yield datos
    cotizaciones.clear_cache()


def _row(fecha, compra, venta):
    return {"casa": "bolsa", "fecha": fecha.isoformat(), "compra": compra, "venta": venta}


def test_promedio_entre_compra_y_venta(fuente):
    fuente["payload"] = [_row(VIERNES, 1190, 1210)]
    assert cotizaciones.mep_promedio(VIERNES) == Decimal("1200.0000")


def test_fin_de_semana_usa_el_dia_habil_anterior(fuente):
    """F-03-CA-4 (dominio): un sábado toma la cotización del viernes."""

    fuente["payload"] = [_row(VIERNES, 1180, 1200), _row(LUNES, 1300, 1320)]
    cotizacion = cotizaciones.mep(SABADO)
    assert cotizacion.fecha == VIERNES and cotizacion.promedio == Decimal("1190.0000")


def test_sin_dato_cercano_devuelve_none(fuente):
    fuente["payload"] = [_row(date(2026, 1, 2), 1000, 1010)]
    assert cotizaciones.mep_promedio(LUNES) is None


def test_fuente_caida_lanza_error(fuente):
    fuente["error"] = "timeout"
    with pytest.raises(cotizaciones.CotizacionError):
        cotizaciones.mep_promedio(LUNES)


def test_cachea_la_serie(fuente):
    fuente["payload"] = [_row(VIERNES, 1190, 1210)]
    cotizaciones.mep_promedio(VIERNES)
    cotizaciones.mep_promedio(SABADO)
    assert fuente["llamadas"] == 1


@pytest.mark.parametrize(
    "fila",
    [
        {"fecha": "2026-10-16", "compra": -1, "venta": 1210},
        {"fecha": "2026-10-16", "compra": "abc", "venta": 1210},
        {"fecha": "no-es-fecha", "compra": 1190, "venta": 1210},
        {"fecha": "2026-10-16", "compra": "NaN", "venta": 1210},
        {"compra": 1190, "venta": 1210},
        "basura",
    ],
)
def test_ignora_filas_invalidas(fuente, fila):
    fuente["payload"] = [fila, _row(date(2026, 10, 15), 1100, 1120)]
    assert cotizaciones.mep(VIERNES).fecha == date(2026, 10, 15)


def test_respuesta_con_formato_inesperado(fuente):
    fuente["payload"] = {"error": "rate limit"}
    with pytest.raises(cotizaciones.CotizacionError):
        cotizaciones.mep_promedio(VIERNES)


def test_fecha_con_hora_se_acepta(fuente):
    fuente["payload"] = [{"fecha": "2026-10-16T00:00:00.000Z", "compra": "1190", "venta": "1210"}]
    assert cotizaciones.mep_promedio(VIERNES) == Decimal("1200.0000")


def test_solo_https(monkeypatch):
    cotizaciones.clear_cache()
    monkeypatch.setattr(
        cotizaciones,
        "settings",
        type("S", (), {"cotizaciones_url": "http://inseguro", "cotizaciones_timeout": 1})(),
    )
    with pytest.raises(cotizaciones.CotizacionError, match="https"):
        cotizaciones._fetch_json()


@pytest.mark.parametrize("compra, venta", [(100000000, 100000000), (0.00001, 0.00001)])
def test_descarta_valores_fuera_de_rango(fuente, compra, venta):
    """Revisión PR #5: valores absurdos de la fuente se tratan como dato inválido."""

    fuente["payload"] = [_row(VIERNES, compra, venta), _row(date(2026, 10, 15), 1100, 1120)]
    assert cotizaciones.mep(VIERNES).fecha == date(2026, 10, 15)
