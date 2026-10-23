"""F-06 · Proveedores domain (#37), against an in-memory fake Supabase."""

from decimal import Decimal

import pytest

from atrium import finanzas, obras, proveedores
from tests.fake_supabase import FakeSupabase, seed_rubros


@pytest.fixture
def db():
    client = FakeSupabase()
    seed_rubros(client)
    return client


def _rubro(db, nombre):
    return finanzas.find_rubros(db, nombre)[0]["id"]


def test_alta_con_todos_los_datos(db):
    p = proveedores.create_proveedor(
        db,
        {
            "nombre": "  Hierros   Sur ",
            "contacto": "Juan Pérez",
            "telefono": "221 555-1234",
            "email": "ventas@hierros.com.ar",
            "web": "hierros.com.ar",
            "cuit": "30712345671",
            "zona": "Berazategui",
            "notas": "Pide seña",
            "rubro_ids": [_rubro(db, "Estructura"), _rubro(db, "Estructura")],
        },
    )
    assert p["nombre"] == "Hierros Sur"
    assert p["web"] == "https://hierros.com.ar"
    assert p["cuit"] == "30-71234567-1"
    assert p["rubro_ids"] == [_rubro(db, "Estructura")]
    assert p["archivado"] is False


@pytest.mark.parametrize("nombre", ["hierros sur", "HIERROS  SUR", "Hiérros Sur"])
def test_nombre_unico_sin_importar_mayusculas_tildes_ni_espacios(db, nombre):
    proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    with pytest.raises(proveedores.ProveedoresError, match="Ya existe el proveedor «Hierros Sur»"):
        proveedores.create_proveedor(db, {"nombre": nombre})


def test_duplicado_de_un_eliminado_avisa_que_se_restaura(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    proveedores.set_archivado(db, p["id"], True)
    with pytest.raises(proveedores.ProveedoresError, match="restauralo"):
        proveedores.create_proveedor(db, {"nombre": "hierros sur"})


@pytest.mark.parametrize(
    ("campo", "valor", "mensaje"),
    [
        ("nombre", "x", "al menos 2 letras"),
        ("email", "no-es-mail", "mail no es válido"),
        ("web", "javascript:alert(1)", "https://"),
        ("web", "http://x.test", "https://"),
        ("cuit", "123", "11 números"),
        ("cuit", "30-71234567-2", "no es válido"),
        ("telefono", "llamame", "teléfono"),
        ("notas", "x" * 1001, "hasta 1000"),
        ("rubro_ids", ["uno"], "rubros"),
    ],
)
def test_datos_invalidos(db, campo, valor, mensaje):
    datos = {"nombre": "Hierros Sur", campo: valor}
    with pytest.raises(proveedores.ProveedoresError, match=mensaje):
        proveedores.create_proveedor(db, datos)


def test_editar_y_no_editar_autor(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    editado = proveedores.update_proveedor(db, p["id"], {"telefono": "11 4444 5555"})
    assert editado["telefono"] == "11 4444 5555"
    with pytest.raises(proveedores.ProveedoresError, match="no se pueden editar"):
        proveedores.update_proveedor(db, p["id"], {"creado_por": "otro"})


def test_editar_sin_chocar_consigo_mismo(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    proveedores.create_proveedor(db, {"nombre": "Marmolería Sur"})
    assert proveedores.update_proveedor(db, p["id"], {"nombre": "HIERROS SUR"})["nombre"] == (
        "HIERROS SUR"
    )
    with pytest.raises(proveedores.ProveedoresError, match="Ya existe"):
        proveedores.update_proveedor(db, p["id"], {"nombre": "marmoleria sur"})


def test_eliminar_archiva_y_restaurar(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    proveedores.set_archivado(db, p["id"], True)
    assert proveedores.list_proveedores(db) == []
    assert [x["nombre"] for x in proveedores.list_proveedores(db, incluir_archivados=True)] == [
        "Hierros Sur"
    ]
    assert proveedores.find_proveedores(db, "hierros") == []
    proveedores.set_archivado(db, p["id"], False)
    assert proveedores.find_proveedores(db, "hierros")[0]["id"] == p["id"]


def test_buscar_y_filtrar(db):
    estructura, pisos = _rubro(db, "Estructura"), _rubro(db, "Pisos y revestimientos")
    proveedores.create_proveedor(
        db, {"nombre": "Hierros Sur", "contacto": "Juan", "rubro_ids": [estructura]}
    )
    proveedores.create_proveedor(db, {"nombre": "Marmolería Sur", "rubro_ids": [pisos]})
    lista = proveedores.list_proveedores(db)
    rubros = {r["id"]: r["nombre"] for r in finanzas.list_rubros(db)}
    assert [p["nombre"] for p in proveedores.filtrar(lista, "marmoleria")] == ["Marmolería Sur"]
    assert [p["nombre"] for p in proveedores.filtrar(lista, "juan")] == ["Hierros Sur"]
    assert [p["nombre"] for p in proveedores.filtrar(lista, "pisos", rubros=rubros)] == [
        "Marmolería Sur"
    ]
    assert [p["nombre"] for p in proveedores.filtrar(lista, rubro_id=estructura)] == ["Hierros Sur"]
    assert len(proveedores.find_proveedores(db, "sur")) == 2
    assert [p["nombre"] for p in proveedores.find_proveedores(db, "hierros sur")] == ["Hierros Sur"]


@pytest.mark.parametrize(
    ("telefono", "tel", "whatsapp"),
    [
        ("221 555-1234", "tel:+542215551234", "https://wa.me/5492215551234"),
        ("0221 555 1234", "tel:+542215551234", "https://wa.me/5492215551234"),
        ("+54 9 11 4444-5555", "tel:+5491144445555", "https://wa.me/5491144445555"),
    ],
)
def test_enlaces_de_contacto(telefono, tel, whatsapp):
    enlaces = dict(
        proveedores.enlaces_contacto(
            {"telefono": telefono, "email": "a@b.com", "web": "https://b.com"}
        )
    )
    assert enlaces["📞 Llamar"] == tel
    assert enlaces["💬 WhatsApp"] == whatsapp
    assert enlaces["✉️ Mail"] == "mailto:a@b.com"
    assert enlaces["🌐 Web"] == "https://b.com"


def test_enlaces_nunca_con_datos_invalidos():
    enlaces = proveedores.enlaces_contacto(
        {"telefono": "abc", "email": "x onerror=", "web": "javascript:alert(1)"}
    )
    assert enlaces == []


def test_calificar_una_por_socio_y_cambiarla(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    proveedores.calificar(db, p["id"], "id-a", 5, "Cumple", autor="a@x")
    proveedores.calificar(db, p["id"], "id-b", 4, None, autor="b@x")
    proveedores.calificar(db, p["id"], "id-a", 3, "Se atrasó", autor="a@x")
    calificaciones = proveedores.list_calificaciones(db, p["id"])
    assert sorted((c["creado_por"], c["estrellas"]) for c in calificaciones) == [
        ("id-a", 3),
        ("id-b", 4),
    ]
    assert proveedores.promedio(calificaciones) == (Decimal("3.5"), 2)
    assert proveedores.promedios(calificaciones)[p["id"]] == (Decimal("3.5"), 2)


@pytest.mark.parametrize("estrellas", [0, 6, "muchas", None])
def test_calificar_fuera_de_rango(db, estrellas):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    with pytest.raises(proveedores.ProveedoresError, match="de 1 a 5"):
        proveedores.calificar(db, p["id"], "id-a", estrellas)


def test_no_se_califica_un_eliminado(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    proveedores.set_archivado(db, p["id"], True)
    with pytest.raises(proveedores.ProveedoresError, match="eliminado"):
        proveedores.calificar(db, p["id"], "id-a", 5)


@pytest.mark.parametrize(
    ("valor", "cantidad", "texto"),
    [
        (Decimal("4.5"), 2, "★★★★☆ 4,5 · 2 calificaciones"),
        (5, 1, "★★★★★ 5,0 · 1 calificación"),
        (None, 0, "Sin calificaciones"),
    ],
)
def test_estrellas_siempre_con_numero(valor, cantidad, texto):
    assert proveedores.estrellas_txt(valor, cantidad) == texto


def _obra_con_item(db, nombre):
    obra = obras.create_obra(db, {"nombre": nombre})
    item, _ = finanzas.add_presupuesto_item(
        db,
        obra["id"],
        monto="0",
        moneda="ARS",
        rubro_id=_rubro(db, "Estructura"),
        tipo_cambio="1200",
    )
    return obra, item


def test_compras_por_obra_y_por_moneda(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    otro = proveedores.create_proveedor(db, {"nombre": "Otro"})
    _, item1 = _obra_con_item(db, "Palmeras 55")
    _, item2 = _obra_con_item(db, "Casa Lote 12")
    for item, monto, moneda in ((item1, 1000, "ARS"), (item1, 500, "ARS"), (item2, 100, "USD")):
        finanzas.add_gasto(
            db,
            item["id"],
            monto=monto,
            moneda=moneda,
            descripcion="x",
            tipo_cambio=1200,
            proveedor_id=p["id"],
        )
    anulado, _ = finanzas.add_gasto(
        db,
        item1["id"],
        monto=999,
        moneda="ARS",
        descripcion="x",
        tipo_cambio=1200,
        proveedor_id=p["id"],
    )
    finanzas.anular_gasto(db, anulado["id"])
    finanzas.add_gasto(
        db,
        item1["id"],
        monto=7,
        moneda="ARS",
        descripcion="x",
        tipo_cambio=1200,
        proveedor_id=otro["id"],
    )

    compras = proveedores.compras(db, p["id"])
    assert compras.cantidad == 3
    assert compras.totales == {"ARS": Decimal("1500"), "USD": Decimal("100")}
    assert compras.total_txt() == "ARS 1.500 · USD 100"
    assert [(o.obra, len(o.gastos)) for o in compras.obras] == [
        ("Casa Lote 12", 1),
        ("Palmeras 55", 2),
    ]
    resumen = proveedores.resumen_compras(db)
    assert resumen[p["id"]].cantidad == 3 and len(resumen[p["id"]].obras) == 2


def test_gasto_con_proveedor_de_la_lista(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    _, item = _obra_con_item(db, "Palmeras 55")
    gasto, _ = finanzas.add_gasto(
        db,
        item["id"],
        monto=10,
        moneda="ARS",
        descripcion="x",
        tipo_cambio=1200,
        proveedor_id=p["id"],
    )
    assert (gasto["proveedor_id"], gasto["proveedor"]) == (p["id"], "Hierros Sur")


def test_gasto_no_elige_un_proveedor_eliminado_pero_lo_conserva(db):
    p = proveedores.create_proveedor(db, {"nombre": "Hierros Sur"})
    _, item = _obra_con_item(db, "Palmeras 55")
    gasto, _ = finanzas.add_gasto(
        db,
        item["id"],
        monto=10,
        moneda="ARS",
        descripcion="x",
        tipo_cambio=1200,
        proveedor_id=p["id"],
    )
    proveedores.set_archivado(db, p["id"], True)
    with pytest.raises(finanzas.FinanzasError, match="fue eliminado"):
        finanzas.add_gasto(
            db,
            item["id"],
            monto=10,
            moneda="ARS",
            descripcion="y",
            tipo_cambio=1200,
            proveedor_id=p["id"],
        )
    editado, _ = finanzas.update_gasto(
        db,
        gasto["id"],
        presupuesto_item_id=item["id"],
        fecha=gasto["fecha"],
        monto=20,
        moneda="ARS",
        descripcion="x",
        proveedor_id=p["id"],
    )
    assert editado["proveedor_id"] == p["id"]
    sin, _ = finanzas.update_gasto(
        db,
        gasto["id"],
        presupuesto_item_id=item["id"],
        fecha=gasto["fecha"],
        monto=20,
        moneda="ARS",
        descripcion="x",
        proveedor_id=None,
    )
    assert sin["proveedor_id"] is None


def test_describe_para_el_agente(db):
    p = proveedores.create_proveedor(
        db,
        {
            "nombre": "Hierros Sur",
            "telefono": "221 555 1234",
            "rubro_ids": [_rubro(db, "Estructura")],
        },
    )
    proveedores.calificar(db, p["id"], "id-a", 5, "Cumple", autor="a@x")
    texto = proveedores.describe_proveedor(
        p,
        {r["id"]: r["nombre"] for r in finanzas.list_rubros(db)},
        proveedores.list_calificaciones(db, p["id"]),
        proveedores.compras(db, p["id"]),
    )
    assert "Hierros Sur" in texto and "Estructura" in texto and "221 555 1234" in texto
    assert "5,0 · 1 calificación" in texto and "«Cumple»" in texto
    assert "Sin compras todavía" in texto
