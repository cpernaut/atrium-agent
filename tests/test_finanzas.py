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


def _item_hierro(db):
    """The budget item gastos go to by default (#35: every gasto has an item)."""

    existente = [i for i in finanzas.list_presupuesto(db, 1) if i.get("descripcion") == "Hierro"]
    if existente:
        return existente[0]["id"]
    item, _ = finanzas.add_presupuesto_item(
        db,
        1,
        monto="1000000",
        moneda="ARS",
        rubro_id=_rubro(db, "Estructura"),
        descripcion="Hierro",
    )
    return item["id"]


def _gasto(db, **cambios):
    item = cambios.pop("item", "hierro")
    datos = {"monto": "350000", "moneda": "ARS", "descripcion": "Hierro"}
    datos.update(cambios)
    return finanzas.add_gasto(db, _item_hierro(db) if item == "hierro" else item, **datos)


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


def test_rubro_desactivado_no_se_ofrece_ni_acepta_items(db, mep):
    rubro_id = _rubro(db, "Pintura")
    finanzas.set_rubro_activo(db, rubro_id, False)
    assert "Pintura" not in [r["nombre"] for r in finanzas.list_rubros(db)]
    assert "Pintura" in [r["nombre"] for r in finanzas.list_rubros(db, incluir_inactivos=True)]
    with pytest.raises(finanzas.FinanzasError, match="desactivado"):
        finanzas.add_presupuesto_item(db, 1, monto=1, moneda="ARS", rubro_id=rubro_id)


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
        ({"item": None}, "Elegí el ítem"),
        ({"item": 999}, "No se encontró el ítem"),
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
    # #35 R16: gastar sin presupuesto es excederse; sin gastos, «Sin presupuesto asignado».
    assert finanzas.estado_desvio(fila.desvio, fila.presupuestado) == "Excedido"
    assert finanzas.estado(Decimal(0), Decimal(0)) == "Sin presupuesto asignado"


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
    # 10 ítems de 50 + el ítem «Hierro» de 1.000.000 al que van los gastos.
    assert (res.gastado, res.presupuestado) == (Decimal("1000"), Decimal("1000500"))
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


# --------------------------------------------------------------------------- #
# Edición y borrado de ítems de presupuesto (F-03 R9, R10)
# --------------------------------------------------------------------------- #
def _item_db(db, **cambios):
    datos = {
        "monto": "1000",
        "moneda": "USD",
        "rubro_id": _rubro(db, "Pintura"),
        "descripcion": "A",
    }
    datos.update(cambios)
    item, _ = finanzas.add_presupuesto_item(db, 1, **datos)
    return item


def _editar(db, item, **cambios):
    datos = {
        "monto": item["monto"],
        "moneda": item["moneda"],
        "rubro_id": item["rubro_id"],
        "descripcion": item.get("descripcion"),
    }
    datos.update(cambios)
    return finanzas.update_presupuesto_item(db, item["id"], **datos)


def test_editar_item_cambia_solo_campos_permitidos(db, mep):
    item = _item_db(db)
    editado = _editar(
        db, item, monto="2.500,50", moneda="ars", rubro_id=_rubro(db, "Estructura"), descripcion="B"
    )
    assert (editado["monto"], editado["moneda"], editado["descripcion"]) == ("2500.50", "ARS", "B")
    assert editado["rubro_id"] == _rubro(db, "Estructura")
    assert (editado["fecha"], editado["obra_id"]) == (item["fecha"], item["obra_id"])
    assert (editado["tipo_cambio"], editado["tipo_cambio_origen"]) == ("1200.0000", "auto")


def test_editar_cotizacion(db, mep):
    item = _item_db(db)
    igual = _editar(db, item, tipo_cambio="1200")
    assert igual["tipo_cambio_origen"] == "auto"  # mismo valor: no cambia el origen
    cambiada = _editar(db, item, tipo_cambio=1150)
    assert (cambiada["tipo_cambio"], cambiada["tipo_cambio_origen"]) == ("1150.0000", "manual")
    vacia = _editar(db, item, tipo_cambio=None)
    assert vacia["tipo_cambio"] == "1150.0000"  # vacío: conserva la actual


def test_editar_item_sin_cotizacion_la_agrega_manual(db, mep):
    mep["valor"] = None
    item = _item_db(db)
    assert "tipo_cambio" not in item
    editado = _editar(db, item, tipo_cambio="1190")
    assert (editado["tipo_cambio"], editado["tipo_cambio_origen"]) == ("1190.0000", "manual")


@pytest.mark.parametrize(
    "cambio, mensaje",
    [
        ({"monto": -5}, "no puede ser negativo"),
        ({"moneda": ""}, "Elegí la moneda"),
        ({"moneda": "EUR"}, "Moneda inválida"),
        ({"rubro_id": None}, "Elegí un rubro"),
        ({"descripcion": "x" * 201}, "hasta 200"),
        ({"tipo_cambio": -5}, "mayor que cero"),
    ],
)
def test_editar_item_invalido_no_cambia_nada(db, mep, cambio, mensaje):
    item = _item_db(db)
    with pytest.raises(finanzas.FinanzasError, match=mensaje):
        _editar(db, item, **cambio)
    assert finanzas.get_presupuesto_item(db, item["id"])["monto"] == item["monto"]


def test_item_borrado_no_se_edita(db, mep):
    item = _item_db(db)
    finanzas.borrar_presupuesto_item(db, item["id"])
    with pytest.raises(finanzas.FinanzasError, match="fue borrado"):
        _editar(db, item, descripcion="Z")
    assert finanzas.get_presupuesto_item(db, item["id"])["anulado"] is True


def test_rubro_desactivado_se_conserva_pero_no_se_elige(db, mep):
    item = _item_db(db)
    finanzas.set_rubro_activo(db, item["rubro_id"], False)
    assert _editar(db, item, descripcion="sigue en Pintura")["rubro_id"] == item["rubro_id"]
    otro = _rubro(db, "Revoques")
    finanzas.set_rubro_activo(db, otro, False)
    with pytest.raises(finanzas.FinanzasError, match="desactivado"):
        _editar(db, item, rubro_id=otro)


def test_editar_item_inexistente(db, mep):
    with pytest.raises(finanzas.FinanzasError, match="No se encontró"):
        finanzas.update_presupuesto_item(db, 999, monto=1, moneda="ARS", rubro_id=1)


# --------------------------------------------------------------------------- #
# #35 · Gastos por ítem, «Imprevistos», monto 0 y semáforo
# --------------------------------------------------------------------------- #
def test_gasto_toma_obra_y_rubro_del_item(db, mep):
    """#35 R11: el gasto pertenece al ítem; obra y rubro salen del ítem."""

    item = _item_db(db, rubro_id=_rubro(db, "Carpinterías"), descripcion="Mesada")
    gasto, _ = finanzas.add_gasto(db, item["id"], monto=10, moneda="ARS", descripcion="Seña")
    assert gasto["presupuesto_item_id"] == item["id"]
    assert (gasto["obra_id"], gasto["rubro_id"]) == (1, item["rubro_id"])


def test_no_se_agregan_gastos_a_un_item_borrado(db, mep):
    item = _item_db(db)
    finanzas.borrar_presupuesto_item(db, item["id"])
    with pytest.raises(finanzas.FinanzasError, match="fue borrado"):
        finanzas.add_gasto(db, item["id"], monto=10, moneda="ARS", descripcion="x")


def test_borrar_item_borra_sus_gastos(db, mep):
    """#35 R12b: borrar un ítem anula el ítem y sus gastos; otros ítems no se tocan."""

    item = _item_db(db)
    otro = _item_db(db, descripcion="Otro")
    for monto in (10, 20):
        finanzas.add_gasto(db, item["id"], monto=monto, moneda="USD", descripcion="g")
    ajeno, _ = finanzas.add_gasto(db, otro["id"], monto=5, moneda="USD", descripcion="h")

    finanzas.borrar_presupuesto_item(db, item["id"])

    gastos = {g["id"]: g for g in finanzas.list_gastos(db, 1)}
    assert len(gastos) == 3  # nada se borra de la base
    assert [g["anulado"] for g in gastos.values() if g["presupuesto_item_id"] == item["id"]] == [
        True,
        True,
    ]
    assert gastos[ajeno["id"]]["anulado"] is False


@pytest.mark.parametrize("monto", [0, "0", "", None, "0,00"])
def test_item_puede_valer_cero(db, mep, monto):
    """#35 D9: se listan ítems y los montos se cargan después."""

    item = _item_db(db, monto=monto)
    assert item["monto"] == "0.00"
    editado = _editar(db, item, monto="1.500")
    assert editado["monto"] == "1500.00"
    assert _editar(db, editado, monto=0)["monto"] == "0.00"


def test_item_en_cero_no_necesita_cotizacion(db, mep):
    mep["valor"] = None
    _item_db(db, monto=0, moneda="USD")
    res = finanzas.resumen(db, 1, "ARS")
    assert not res.incompleto and res.presupuestado == 0


@pytest.mark.parametrize(
    "presupuesto, moneda, esperado",
    [("50000000", "ARS", "5000000.00"), ("37000", "USD", "3700.00"), (None, "ARS", "0.00")],
)
def test_crear_imprevistos(db, mep, presupuesto, moneda, esperado):
    """#35 R12: 10 % del presupuesto de la obra, en su moneda, rubro Otros."""

    obra = {"id": 1, "presupuesto": presupuesto, "moneda": moneda}
    item, aviso = finanzas.crear_imprevistos(db, obra)
    assert aviso is None
    assert (item["monto"], item["moneda"], item["descripcion"]) == (esperado, moneda, "Imprevistos")
    assert item["rubro_id"] == _rubro(db, "Otros") and item["es_imprevistos"] is True
    assert ("tipo_cambio" in item) == (esperado != "0.00")
    assert finanzas.imprevistos_vigente(finanzas.list_presupuesto(db, 1))["id"] == item["id"]


def test_un_solo_imprevistos_vigente(db, mep):
    item, _ = finanzas.crear_imprevistos(db, {"id": 1, "presupuesto": None, "moneda": "ARS"})
    with pytest.raises(finanzas.FinanzasError, match="ya tiene un ítem de imprevistos"):
        _item_db(db, es_imprevistos=True)
    finanzas.borrar_presupuesto_item(db, item["id"])
    nuevo = _item_db(db, es_imprevistos=True, descripcion="Imprevistos")
    assert nuevo["es_imprevistos"] is True


def test_completar_cotizacion_de_imprevistos_de_la_migracion(db, mep):
    """Los «Imprevistos» que crea la migración (sin MEP) lo completan al mostrarse."""

    db.table("presupuesto_items").insert(
        {
            "obra_id": 1,
            "rubro_id": _rubro(db, "Otros"),
            "monto": "3700.00",
            "moneda": "USD",
            "fecha": finanzas.hoy().isoformat(),
            "es_imprevistos": True,
        }
    ).execute()
    _item_db(db, monto=10)  # otro ítem: no se toca
    items = finanzas.completar_cotizacion_imprevistos(db, finanzas.list_presupuesto(db, 1))
    imprevistos = finanzas.imprevistos_vigente(items)
    assert (imprevistos["tipo_cambio"], imprevistos["tipo_cambio_origen"]) == ("1200.0000", "auto")
    mep["error"] = "caído"
    assert finanzas.completar_cotizacion_imprevistos(db, items) == items  # nunca falla


def test_resumen_por_item(db, mep):
    """#35 CA-26/31: total, gastado, saldo y % por ítem, cada gasto con su cotización."""

    item = _item_db(db, monto="1000000", moneda="ARS", descripcion="Hierro del 8")
    finanzas.add_gasto(db, item["id"], monto="500", moneda="USD", descripcion="a")  # 600.000
    finanzas.add_gasto(db, item["id"], monto="100000", moneda="ARS", descripcion="b")
    anulado, _ = finanzas.add_gasto(db, item["id"], monto="5", moneda="ARS", descripcion="c")
    finanzas.anular_gasto(db, anulado["id"])

    fila = finanzas.resumen(db, 1, "ARS").items[item["id"]]
    assert (fila.presupuestado, fila.gastado, fila.saldo) == (
        Decimal("1000000"),
        Decimal("700000"),
        Decimal("300000"),
    )
    assert fila.ejecutado == Decimal("0.7") and len(fila.gastos) == 3
    assert len(fila.gastos_vigentes) == 2


def test_gasto_en_otra_moneda_sin_cotizacion_marca_el_item_incompleto(db, mep):
    item = _item_db(db, monto="1000", moneda="ARS")
    mep["valor"] = None
    finanzas.add_gasto(db, item["id"], monto="10", moneda="USD", descripcion="x")
    res = finanzas.resumen(db, 1, "ARS")
    assert res.items[item["id"]].sin_convertir and res.incompleto


def test_cambiar_rubro_del_item_mueve_sus_gastos(db, mep):
    """#35 CA-35: el resumen por rubro sigue al ítem."""

    item = _item_db(db, monto="100", moneda="ARS", rubro_id=_rubro(db, "Pintura"))
    finanzas.add_gasto(db, item["id"], monto="40", moneda="ARS", descripcion="x")
    _editar(db, item, rubro_id=_rubro(db, "Revoques"))
    filas = {f.rubro: f for f in finanzas.resumen(db, 1, "ARS").filas}
    assert "Pintura" not in filas
    assert (filas["Revoques"].presupuestado, filas["Revoques"].gastado) == (100, 40)


@pytest.mark.parametrize(
    "gastado, presupuestado, esperado",
    [
        ("0", "100", "Dentro del presupuesto"),
        ("89.99", "100", "Dentro del presupuesto"),
        ("90", "100", "Cerca del límite"),
        ("100", "100", "Cerca del límite"),
        ("100.01", "100", "Excedido"),
        ("1", "0", "Excedido"),
        ("0", "0", "Sin presupuesto asignado"),
    ],
)
def test_semaforo(gastado, presupuestado, esperado):
    """#35 R16: verde < 90 %, amarillo 90-100 %, rojo > 100 %, siempre en palabras."""

    assert finanzas.estado(Decimal(gastado), Decimal(presupuestado)) == esperado
    assert finanzas.estado_con_icono(Decimal(gastado), Decimal(presupuestado)).endswith(esperado)


def test_describe_resumen_incluye_items(db, mep):
    item = _item_db(db, monto="1000", moneda="ARS", descripcion="Mesada")
    finanzas.add_gasto(db, item["id"], monto="950", moneda="ARS", descripcion="x")
    texto = finanzas.describe_resumen(finanzas.resumen(db, 1, "ARS"), "Casa")
    assert "- Mesada: total ARS 1.000, gastado ARS 950 (95%), saldo ARS 50, 1 gasto(s)" in texto
    assert "(Cerca del límite)" in texto


def test_completar_cotizacion_no_pisa_una_manual_concurrente(db, mep, monkeypatch):
    """Revisión PR #38 / R4: si alguien guarda una cotización manual entre la lectura
    y la escritura, la automática no la reemplaza."""

    db.table("presupuesto_items").insert(
        {
            "obra_id": 1,
            "rubro_id": _rubro(db, "Otros"),
            "monto": "3700.00",
            "moneda": "USD",
            "fecha": finanzas.hoy().isoformat(),
            "es_imprevistos": True,
        }
    ).execute()
    leidos = finanzas.list_presupuesto(db, 1)  # lectura sin cotización
    item_id = leidos[0]["id"]
    real = finanzas.cotizar

    def cotizar_mientras_otro_corrige(fecha):
        finanzas.set_tipo_cambio(db, "presupuesto_items", item_id, "1111")
        return real(fecha)

    monkeypatch.setattr(finanzas, "cotizar", cotizar_mientras_otro_corrige)
    resultado = finanzas.completar_cotizacion_imprevistos(db, leidos)

    guardado = finanzas.get_presupuesto_item(db, item_id)
    assert (guardado["tipo_cambio"], guardado["tipo_cambio_origen"]) == ("1111.0000", "manual")
    assert resultado[0]["tipo_cambio_origen"] == "manual"  # devuelve el valor vigente


def test_item_con_rubro_desactivado_no_acepta_gastos_nuevos(db, mep):
    """Revisión PR #38 / R7: un rubro desactivado no recibe cargas nuevas, tampoco
    gastos en ítems que ya lo tenían; el historial se conserva."""

    item = _item_db(db, rubro_id=_rubro(db, "Pintura"))
    viejo, _ = finanzas.add_gasto(db, item["id"], monto=10, moneda="USD", descripcion="antes")
    finanzas.set_rubro_activo(db, item["rubro_id"], False)

    with pytest.raises(finanzas.FinanzasError, match="desactivado"):
        finanzas.add_gasto(db, item["id"], monto=10, moneda="USD", descripcion="después")
    assert [g["id"] for g in finanzas.list_gastos(db, 1)] == [viejo["id"]]
    otro = _rubro(db, "Revoques")
    _editar(db, item, rubro_id=otro)  # lo pasa a un rubro activo...
    finanzas.add_gasto(db, item["id"], monto=10, moneda="USD", descripcion="después")  # ...y sí


# --------------------------------------------------------------------------- #
# #25 · Editar un gasto
# --------------------------------------------------------------------------- #
def _editar_gasto(db, gasto, **cambios):
    datos = {
        "presupuesto_item_id": gasto["presupuesto_item_id"],
        "fecha": gasto["fecha"],
        "monto": gasto["monto"],
        "moneda": gasto["moneda"],
        "descripcion": gasto["descripcion"],
        "proveedor": gasto.get("proveedor"),
    }
    datos.update(cambios)
    return finanzas.update_gasto(db, gasto["id"], **datos)


def test_editar_gasto_cambia_todos_sus_datos(db, mep):
    """#25: monto, moneda, descripción, proveedor y fecha se editan; obra y autor no."""

    gasto, _ = _gasto(db)
    ayer = finanzas.hoy() - timedelta(days=1)
    editado, aviso = _editar_gasto(
        db,
        gasto,
        monto="400.000",
        moneda="usd",
        descripcion="Hierro 10",
        proveedor="HS",
        fecha=ayer,
    )
    assert aviso is None
    assert (editado["monto"], editado["moneda"], editado["descripcion"], editado["proveedor"]) == (
        "400000.00",
        "USD",
        "Hierro 10",
        "HS",
    )
    assert editado["fecha"] == ayer.isoformat() and editado["obra_id"] == gasto["obra_id"]


def test_editar_gasto_lo_mueve_a_otro_item(db, mep):
    """#25: el gasto se mueve a otro ítem de la obra y su rubro pasa a ser el del ítem."""

    gasto, _ = _gasto(db)
    otro = _item_db(db, rubro_id=_rubro(db, "Carpinterías"), descripcion="Mesada")
    movido, _ = _editar_gasto(db, gasto, presupuesto_item_id=otro["id"])
    assert movido["presupuesto_item_id"] == otro["id"]
    assert movido["rubro_id"] == otro["rubro_id"]
    filas = {f.rubro: f for f in finanzas.resumen(db, 1, "ARS").filas}
    assert filas["Carpinterías"].gastado == Decimal("350000")


def test_editar_gasto_no_mueve_a_item_borrado_ni_de_otra_obra(db, mep):
    gasto, _ = _gasto(db)
    borrado = _item_db(db, descripcion="Borrado")
    finanzas.borrar_presupuesto_item(db, borrado["id"])
    with pytest.raises(finanzas.FinanzasError, match="fue borrado"):
        _editar_gasto(db, gasto, presupuesto_item_id=borrado["id"])
    db.table("obras").insert({"nombre": "Otra"}).execute()
    ajeno, _ = finanzas.add_presupuesto_item(
        db, 2, monto=1, moneda="ARS", rubro_id=_rubro(db, "Pintura")
    )
    with pytest.raises(finanzas.FinanzasError, match="otra obra"):
        _editar_gasto(db, gasto, presupuesto_item_id=ajeno["id"])


def test_editar_gasto_recalcula_la_cotizacion_automatica_si_cambia_la_fecha(db, mep):
    """#25 (decisión): con cotización automática, cambiar la fecha la recalcula; una
    corregida a mano se respeta."""

    gasto, _ = _gasto(db)  # MEP 1200, automática
    mep["valor"] = Decimal("1100")
    ayer = finanzas.hoy() - timedelta(days=1)
    editado, _ = _editar_gasto(db, gasto, fecha=ayer, tipo_cambio=gasto["tipo_cambio"])
    assert (editado["tipo_cambio"], editado["tipo_cambio_origen"]) == ("1100.0000", "auto")

    manual, _ = _editar_gasto(db, editado, tipo_cambio="1050")
    assert (manual["tipo_cambio"], manual["tipo_cambio_origen"]) == ("1050.0000", "manual")
    mep["valor"] = Decimal("1300")
    otra_fecha, _ = _editar_gasto(db, manual, fecha=finanzas.hoy(), tipo_cambio="1050")
    assert (otra_fecha["tipo_cambio"], otra_fecha["tipo_cambio_origen"]) == ("1050.0000", "manual")


def test_editar_gasto_sin_cotizacion_para_la_nueva_fecha_avisa(db, mep):
    gasto, _ = _gasto(db)
    mep["valor"] = None
    editado, aviso = _editar_gasto(db, gasto, fecha=finanzas.hoy() - timedelta(days=2))
    assert editado["tipo_cambio"] is None and "No hay cotización" in aviso


@pytest.mark.parametrize(
    "cambio, mensaje",
    [
        ({"monto": 0}, "mayor que cero"),
        ({"descripcion": " "}, "Falta la descripción"),
        ({"moneda": "EUR"}, "Moneda inválida"),
        ({"fecha": "2999-01-01"}, "futura"),
        ({"presupuesto_item_id": None}, "Elegí el ítem"),
        ({"tipo_cambio": 0}, "mayor que cero"),
        ({"tipo_cambio": 0.0}, "mayor que cero"),
        ({"tipo_cambio": -3}, "mayor que cero"),
    ],
)
def test_editar_gasto_invalido_no_cambia_nada(db, mep, cambio, mensaje):
    gasto, _ = _gasto(db)
    with pytest.raises(finanzas.FinanzasError, match=mensaje):
        _editar_gasto(db, gasto, **cambio)
    assert finanzas.get_gasto(db, gasto["id"])["monto"] == gasto["monto"]


def test_gasto_anulado_no_se_edita(db, mep):
    gasto, _ = _gasto(db)
    finanzas.anular_gasto(db, gasto["id"])
    with pytest.raises(finanzas.FinanzasError, match="anulado"):
        _editar_gasto(db, gasto, descripcion="x")


def test_editar_gasto_solo_envia_campos_permitidos(db, mep, monkeypatch):
    gasto, _ = _gasto(db)
    enviados = []
    original = db.table

    def espiar(nombre):
        query = original(nombre)
        update = query.update

        def registrar(payload):
            enviados.append((nombre, dict(payload)))
            return update(payload)

        query.update = registrar
        return query

    monkeypatch.setattr(db, "table", espiar)
    _editar_gasto(db, gasto, descripcion="otra")
    assert enviados and all(
        set(p) <= set(finanzas.CAMPOS_EDITABLES_GASTO) for t, p in enviados if t == "gastos"
    )


# --------------------------------------------------------------------------- #
# #49 · Pantalla de rubros: ordenar y desactivar
# --------------------------------------------------------------------------- #
def _nombres(db):
    return [r["nombre"] for r in finanzas.list_rubros(db, incluir_inactivos=True)]


def test_mover_rubro_arriba_y_abajo(db):
    nombres = _nombres(db)
    segundo = finanzas.find_rubros(db, nombres[1])[0]
    finanzas.mover_rubro(db, segundo["id"], -1)
    assert _nombres(db)[:2] == [nombres[1], nombres[0]]
    finanzas.mover_rubro(db, segundo["id"], 1)
    assert _nombres(db) == nombres


def test_mover_rubro_en_los_extremos_no_hace_nada(db):
    rubros = finanzas.list_rubros(db, incluir_inactivos=True)
    assert finanzas.mover_rubro(db, rubros[0]["id"], -1) == []
    assert finanzas.mover_rubro(db, rubros[-1]["id"], 1) == []


def test_mover_rubro_con_ordenes_repetidos(db):
    a = finanzas.create_rubro(db, "Zeta", orden=500)
    b = finanzas.create_rubro(db, "Alfa", orden=500)  # mismo orden: va por nombre
    nombres = _nombres(db)
    assert nombres.index("Alfa") + 1 == nombres.index("Zeta")
    finanzas.mover_rubro(db, a["id"], -1)
    nombres = _nombres(db)
    assert nombres.index("Zeta") + 1 == nombres.index("Alfa")
    assert b["id"] != a["id"]


@pytest.mark.parametrize("paso", [0, 2, -2])
def test_mover_rubro_paso_invalido(db, paso):
    with pytest.raises(finanzas.FinanzasError):
        finanzas.mover_rubro(db, 1, paso)


def test_mover_rubro_inexistente(db):
    with pytest.raises(finanzas.FinanzasError, match="No se encontró"):
        finanzas.mover_rubro(db, 9999, 1)


def test_otros_no_se_desactiva(db):
    otros = finanzas.find_rubros(db, "Otros")[0]
    with pytest.raises(finanzas.FinanzasError, match="«Otros» no se puede desactivar"):
        finanzas.set_rubro_activo(db, otros["id"], False)
    assert finanzas.set_rubro_activo(db, otros["id"], True)["activo"]
