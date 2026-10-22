"""F-03 domain: rubros, gastos, presupuesto, conversion and summary."""

import re
from datetime import timedelta
from decimal import Decimal

import pytest

from atrium import cotizaciones, finanzas
from atrium.config import REPO_ROOT
from tests.fake_supabase import FakeSupabase, seed_rubros


@pytest.fixture
def mep(monkeypatch):
    """Control the MEP rate: a Decimal, None (no quote) or an exception message."""

    estado = {"valor": Decimal("1200"), "error": None}

    def fake(fecha):
        if estado["error"]:
            raise cotizaciones.CotizacionError(estado["error"])
        return estado["valor"]

    monkeypatch.setattr(cotizaciones, "mep_promedio", fake)
    return estado


@pytest.fixture
def db():
    client = FakeSupabase()
    seed_rubros(client)
    client.table("obras").insert({"nombre": "Casa Lote 12"}).execute()
    return client


def _rubro(db, nombre):
    return finanzas.find_rubros(db, nombre)[0]["id"]


def _gasto(db, **cambios):
    datos = {
        "monto": "350000",
        "moneda": "ARS",
        "rubro_id": _rubro(db, "Estructura"),
        "descripcion": "Hierro",
    }
    datos.update(cambios)
    return finanzas.add_gasto(db, 1, **datos)


# --------------------------------------------------------------------------- #
# Rubros
# --------------------------------------------------------------------------- #
def test_precarga_coincide_con_el_esquema():
    """La lista en Python es la misma, en el mismo orden, que la del SQL."""

    sql = (REPO_ROOT / "supabase_schema.sql").read_text(encoding="utf-8")
    bloque = sql.split("insert into public.rubros (nombre, orden) values", 1)[1].split(";", 1)[0]
    en_sql = [(n, int(o)) for n, o in re.findall(r"\('([^']+)',\s*(\d+)\)", bloque)]
    assert en_sql == list(finanzas.RUBROS_INICIALES)
    assert ("Steel frame", 50) in en_sql


def test_rubros_ordenados(db):
    nombres = [r["nombre"] for r in finanzas.list_rubros(db)]
    assert nombres[:5] == [
        "Trabajos preliminares",
        "Movimiento de suelo",
        "Fundaciones",
        "Estructura",
        "Steel frame",
    ]
    assert nombres[-1] == "Otros"


def test_crear_rubro_queda_antes_de_otros(db):
    nuevo = finanzas.create_rubro(db, "  Piscina   y solárium ")
    assert nuevo["nombre"] == "Piscina y solárium"
    nombres = [r["nombre"] for r in finanzas.list_rubros(db)]
    assert nombres[-2:] == ["Piscina y solárium", "Otros"]


@pytest.mark.parametrize("nombre", ["estructura", "ESTRUCTURA ", "Mamposteria", "steel  FRAME"])
def test_crear_rubro_duplicado(db, nombre):
    with pytest.raises(finanzas.FinanzasError, match="Ya existe"):
        finanzas.create_rubro(db, nombre)


@pytest.mark.parametrize("nombre", ["", "   ", "x", "a" * 61])
def test_crear_rubro_nombre_invalido(db, nombre):
    with pytest.raises(finanzas.FinanzasError):
        finanzas.create_rubro(db, nombre)


def test_rubro_desactivado_no_se_ofrece_ni_acepta_gastos(db, mep):
    rubro_id = _rubro(db, "Pintura")
    finanzas.set_rubro_activo(db, rubro_id, False)
    assert "Pintura" not in [r["nombre"] for r in finanzas.list_rubros(db)]
    assert "Pintura" in [r["nombre"] for r in finanzas.list_rubros(db, incluir_inactivos=True)]
    with pytest.raises(finanzas.FinanzasError, match="desactivado"):
        _gasto(db, rubro_id=rubro_id)


def test_buscar_rubro_sin_tildes_y_parcial(db):
    assert [r["nombre"] for r in finanzas.find_rubros(db, "mamposteria")] == ["Mampostería"]
    assert len(finanzas.find_rubros(db, "instalación")) == 3
    assert finanzas.find_rubros(db, "inexistente") == []


# --------------------------------------------------------------------------- #
# Gastos y cotización
# --------------------------------------------------------------------------- #
def test_gasto_con_cotizacion_automatica(db, mep):
    """F-03-CA-3 (dominio)."""

    gasto, aviso = _gasto(db)
    assert aviso is None
    assert (gasto["tipo_cambio"], gasto["tipo_cambio_origen"]) == ("1200.0000", "auto")
    assert gasto["monto"] == "350000.00" and gasto["fecha"] == finanzas.hoy().isoformat()


def test_gasto_en_pesos_tambien_guarda_cotizacion(db, mep):
    gasto, _ = _gasto(db, moneda="ARS")
    assert gasto["tipo_cambio"] == "1200.0000"


def test_fuente_caida_guarda_sin_cotizacion(db, mep):
    """F-03-CA-5 (dominio)."""

    mep["error"] = "timeout"
    gasto, aviso = _gasto(db)
    assert "tipo_cambio" not in gasto and "no se pudo consultar" in aviso.lower()
    assert len(finanzas.list_gastos(db, 1)) == 1


def test_sin_cotizacion_para_la_fecha(db, mep):
    mep["valor"] = None
    gasto, aviso = _gasto(db)
    assert "tipo_cambio" not in gasto and "No hay cotización" in aviso


def test_cotizacion_manual_al_cargar(db, mep):
    gasto, aviso = _gasto(db, tipo_cambio="1.180,5")
    assert (gasto["tipo_cambio"], gasto["tipo_cambio_origen"]) == ("1180.5000", "manual")


def test_corregir_cotizacion(db, mep):
    """F-03-CA-6 (dominio)."""

    gasto, _ = _gasto(db)
    corregido = finanzas.set_tipo_cambio(db, "gastos", gasto["id"], 1180)
    assert (corregido["tipo_cambio"], corregido["tipo_cambio_origen"]) == ("1180.0000", "manual")
    with pytest.raises(finanzas.FinanzasError):
        finanzas.set_tipo_cambio(db, "obras", 1, 1180)


@pytest.mark.parametrize(
    "cambio, mensaje",
    [
        ({"monto": 0}, "mayor que cero"),
        ({"monto": -5}, "mayor que cero"),
        ({"monto": "abc"}, "no es un número"),
        ({"monto": "1e20"}, "demasiado grande"),
        ({"descripcion": "   "}, "Falta la descripción"),
        ({"descripcion": "x" * 201}, "hasta 200"),
        ({"proveedor": "x" * 121}, "hasta 120"),
        ({"moneda": "EUR"}, "Moneda inválida"),
        ({"rubro_id": None}, "Elegí un rubro"),
        ({"rubro_id": 999}, "no existe"),
        ({"fecha": "ayer"}, "Fecha inválida"),
        ({"tipo_cambio": -1}, "mayor que cero"),
    ],
)
def test_gasto_invalido(db, mep, cambio, mensaje):
    """F-03-CA-10 (dominio)."""

    with pytest.raises(finanzas.FinanzasError, match=mensaje):
        _gasto(db, **cambio)
    assert finanzas.list_gastos(db, 1) == []


def test_gasto_con_fecha_futura(db, mep):
    with pytest.raises(finanzas.FinanzasError, match="futura"):
        _gasto(db, fecha=finanzas.hoy() + timedelta(days=1))


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("350.000", "350000.00"),
        ("1.234,50", "1234.50"),
        ("1234,5", "1234.50"),
        (1500.555, "1500.56"),
        ("0.5", "0.50"),
        ("12.5", "12.50"),
        ("0.001", None),  # empieza con 0: no es separador de miles -> redondea a 0
    ],
)
def test_montos_en_formato_argentino(texto, esperado):
    if esperado is None:
        with pytest.raises(finanzas.FinanzasError, match="mayor que cero"):
            finanzas.parse_monto(texto)
    else:
        assert str(finanzas.parse_monto(texto)) == esperado


@pytest.mark.parametrize("moneda", ["pesos", "$", "usd", "U$S", "dólares"])
def test_monedas_coloquiales(db, mep, moneda):
    gasto, _ = _gasto(db, moneda=moneda)
    assert gasto["moneda"] in ("ARS", "USD")


def test_anular_gasto(db, mep):
    gasto, _ = _gasto(db)
    finanzas.anular_gasto(db, gasto["id"])
    assert finanzas.list_gastos(db, 1)[0]["anulado"] is True
    with pytest.raises(finanzas.FinanzasError):
        finanzas.anular_gasto(db, 999)


# --------------------------------------------------------------------------- #
# Conversión y resumen
# --------------------------------------------------------------------------- #
def _fila(rubro_id, monto, moneda, tc="1200", anulado=False):
    return {
        "rubro_id": rubro_id,
        "monto": monto,
        "moneda": moneda,
        "tipo_cambio": tc,
        "anulado": anulado,
    }


RUBROS = [
    {"id": 1, "nombre": "Fundaciones", "orden": 30},
    {"id": 2, "nombre": "Estructura", "orden": 40},
]


def test_conversion_con_la_cotizacion_de_cada_gasto():
    """F-03-CA-7: USD 1.000 y ARS 600.000 a 1200 = ARS 1.800.000 = USD 1.500."""

    gastos = [_fila(2, "1000", "USD"), _fila(2, "600000", "ARS")]
    en_ars = finanzas.calcular_resumen([], gastos, RUBROS, "ARS")
    en_usd = finanzas.calcular_resumen([], gastos, RUBROS, "USD")
    assert en_ars.gastado == Decimal("1800000")
    assert en_usd.gastado == Decimal("1500")


def test_sin_cotizacion_no_se_convierte():
    """F-03-CA-8: el gasto sin cotización no suma y el total queda incompleto."""

    gastos = [_fila(2, "1000", "USD", tc=None), _fila(2, "600000", "ARS", tc=None)]
    res = finanzas.calcular_resumen([], gastos, RUBROS, "ARS")
    assert res.gastado == Decimal("600000")  # misma moneda: no necesita cotización
    assert res.incompleto and len(res.sin_convertir) == 1


def test_anulados_no_cuentan():
    """F-03-CA-9 (cálculo)."""

    gastos = [_fila(2, "100", "ARS"), _fila(2, "900", "ARS", anulado=True)]
    items = [_fila(2, "500", "ARS"), _fila(1, "1", "ARS", anulado=True)]
    res = finanzas.calcular_resumen(items, gastos, RUBROS, "ARS")
    assert (res.presupuestado, res.gastado) == (Decimal("500"), Decimal("100"))
    assert [f.rubro for f in res.filas] == ["Estructura"]


def test_desvio_y_ejecutado_por_rubro():
    items = [_fila(1, "1000", "ARS"), _fila(2, "2000", "ARS")]
    gastos = [_fila(1, "1500", "ARS"), _fila(2, "500", "ARS")]
    res = finanzas.calcular_resumen(items, gastos, RUBROS, "ARS")
    fundaciones, estructura = res.filas
    assert (fundaciones.desvio, fundaciones.ejecutado) == (Decimal("500"), Decimal("1.5"))
    assert finanzas.estado_desvio(fundaciones.desvio, fundaciones.presupuestado) == "Excedido"
    assert finanzas.estado_desvio(estructura.desvio, estructura.presupuestado) == (
        "Dentro del presupuesto"
    )
    assert res.desvio == Decimal("-1000")


def test_rubro_sin_presupuesto():
    res = finanzas.calcular_resumen([], [_fila(1, "10", "ARS")], RUBROS, "ARS")
    fila = res.filas[0]
    assert fila.ejecutado is None
    assert finanzas.formato_porcentaje(fila.ejecutado) == "sin presupuesto"
    assert finanzas.estado_desvio(fila.desvio, fila.presupuestado) == "Sin presupuesto"


def test_presupuesto_usa_mep_del_dia(db, mep):
    """F-03 D7: los ítems también guardan el MEP promedio de su fecha."""

    item, aviso = finanzas.add_presupuesto_item(
        db, 1, monto="5000", moneda="USD", rubro_id=_rubro(db, "Honorarios")
    )
    assert aviso is None
    assert (item["tipo_cambio"], item["tipo_cambio_origen"]) == ("1200.0000", "auto")
    assert item["fecha"] == finanzas.hoy().isoformat()


@pytest.mark.parametrize(
    "valor, moneda, esperado",
    [
        ("1800000", "ARS", "ARS 1.800.000"),
        ("1500.5", "USD", "USD 1.500,50"),
        ("-250000", "ARS", "−ARS 250.000"),
        ("0", "USD", "USD 0"),
    ],
)
def test_formato_es_ar(valor, moneda, esperado):
    assert finanzas.formato_monto(valor, moneda) == esperado


def test_describe_resumen_avisa_total_incompleto():
    gastos = [_fila(2, "1000", "USD", tc=None)]
    texto = finanzas.describe_resumen(finanzas.calcular_resumen([], gastos, RUBROS, "ARS"), "X")
    assert "incompleto" in texto


@pytest.mark.parametrize("orden", ["abc", -1, 200000])
def test_crear_rubro_orden_invalido(db, orden):
    with pytest.raises(finanzas.FinanzasError, match="orden"):
        finanzas.create_rubro(db, "Piscina", orden=orden)


def test_resumen_trae_todas_las_paginas(db, mep, monkeypatch):
    """Revisión PR #5: con más filas que el máximo por respuesta, el resumen no se corta."""

    monkeypatch.setattr(finanzas, "_PAGINA", 4)
    db.max_rows_por_respuesta = 3  # el servidor devuelve aún menos que lo pedido
    for _ in range(10):
        _gasto(db, monto="100")
        finanzas.add_presupuesto_item(
            db, 1, monto="50", moneda="ARS", rubro_id=_rubro(db, "Pintura")
        )

    assert len(finanzas.list_gastos(db, 1)) == 10
    res = finanzas.resumen(db, 1, "ARS")
    assert (res.gastado, res.presupuestado) == (Decimal("1000"), Decimal("500"))
    assert len(finanzas.list_rubros(db)) == len(finanzas.RUBROS_INICIALES)
    assert len(finanzas.list_gastos(db, 1, limit=2)) == 2


def test_paginas_sin_fin_se_cortan(db, monkeypatch):
    monkeypatch.setattr(finanzas, "_MAX_PAGINAS", 2)
    monkeypatch.setattr(finanzas, "_PAGINA", 5)
    with pytest.raises(finanzas.FinanzasError, match="demasiados"):
        finanzas.list_rubros(db)  # 18 rubros > 2 páginas de 5


@pytest.mark.parametrize("valor", ["-1e30", "-" + "9" * 40, -(10**20)])
def test_montos_negativos_enormes_dan_error_claro(valor):
    """Revisión PR #5: un negativo enorme se rechaza antes de redondear."""

    for parse in (finanzas.parse_monto, finanzas.parse_tipo_cambio):
        with pytest.raises(finanzas.FinanzasError, match="mayor que cero"):
            parse(valor)


@pytest.mark.parametrize("valor", ["1e30", "9" * 40, 10**20])
def test_montos_enormes_dan_error_claro(valor):
    """Revisión PR #5: un monto enorme no rompe con InvalidOperation."""

    with pytest.raises(finanzas.FinanzasError, match="demasiado grande"):
        finanzas.parse_monto(valor)
    with pytest.raises(finanzas.FinanzasError, match="demasiado grande"):
        finanzas.parse_tipo_cambio(valor)


@pytest.mark.parametrize("valor", ["0.001", "0.00001"])
def test_tipo_cambio_que_redondea_a_cero(valor):
    with pytest.raises(finanzas.FinanzasError, match="mayor que cero"):
        finanzas.parse_monto(valor) if valor == "0.001" else finanzas.parse_tipo_cambio(valor)


@pytest.mark.parametrize("absurdo", [Decimal("100000000"), Decimal("0.00001")])
def test_cotizacion_absurda_no_impide_guardar(db, mep, absurdo):
    """Revisión PR #5 / R3: una cotización inválida se descarta y el gasto se guarda."""

    mep["valor"] = absurdo
    gasto, aviso = _gasto(db)
    assert "tipo_cambio" not in gasto and aviso
    assert len(finanzas.list_gastos(db, 1)) == 1
