# F-03 · Presupuesto y gastos

**Estado:** Lista
**Prioridad:** Alta
**Depende de:** F-02

## Objetivo

Saber en todo momento cuánto se presupuestó, cuánto se gastó y dónde está el
desvío de cada obra, en pesos y en dólares, sin planillas aparte.

## Historias

- Como **socio**, quiero cargar el presupuesto de una obra por rubro para
  tener una referencia contra la cual medir.
- Como **socio**, quiero registrar un gasto en el momento, desde el celular,
  para no olvidármelo.
- Como **socio**, quiero ver gastado contra presupuestado por rubro, en pesos o
  en dólares MEP, para detectar desvíos a tiempo.
- Como **socio**, quiero decirle al agente «cargá un gasto de 350 mil pesos
  en hierro para Lote 12» y que quede registrado.

## Alcance

**Incluye**
- Lista de **rubros** común a todas las obras, precargada y ampliable.
- Ítems de presupuesto por obra: rubro, descripción, monto y moneda (cada ítem
  en la suya).
- Gastos: fecha, rubro, descripción, proveedor, monto y moneda.
- **Cotización del dólar MEP automática**: cada gasto e ítem de presupuesto
  guarda el MEP **promedio** de su fecha, traído de internet. Se puede corregir
  a mano y queda registrado si fue automático o manual.
- Resumen por obra: presupuestado, gastado, desvío y porcentaje ejecutado,
  por rubro y total, en una **moneda de visualización** (ARS o USD).
- Herramientas del agente para cargar gastos y consultar el resumen.
- Anular un gasto mal cargado (no se borra).

**No incluye** (por ahora)
- Ingresos, señas, aportes de socios y rentabilidad: van en una ficha aparte,
  «Flujo de fondos».
- Comprobantes adjuntos: llegan con F-05, ligados al gasto.
- Otros dólares (oficial, blue): la referencia es siempre el MEP.
- Pagos en cuotas, cuentas corrientes con proveedores, IVA.
- Ajuste por inflación de presupuestos en pesos.

## Datos

**`rubros`** — lista compartida.

| Campo | Tipo | Reglas |
|---|---|---|
| id | bigint | PK |
| nombre | text | único, no vacío |
| orden | int | para mostrarlos en orden de obra |
| activo | bool | default `true`; se desactiva en vez de borrar |

Precarga, en este orden: Trabajos preliminares · Movimiento de suelo ·
Fundaciones · Estructura · **Steel frame** · Mampostería · Cubierta ·
Instalación sanitaria · Instalación eléctrica · Instalación de gas · Revoques ·
Contrapisos y carpetas · Pisos y revestimientos · Carpinterías · Pintura ·
Honorarios y trámites · Limpieza final · Otros.

**`presupuesto_items`**

| Campo | Tipo | Reglas |
|---|---|---|
| obra_id | bigint | FK `obras`, cascade |
| rubro_id | bigint | FK `rubros` |
| descripcion | text | opcional |
| monto | numeric(14,2) | > 0 |
| moneda | text | `ARS` o `USD` |
| fecha | date | default hoy; fecha de la cotización |
| tipo_cambio | numeric(12,4) | ARS por USD (MEP promedio); > 0 o vacío |
| tipo_cambio_origen | text | `auto` o `manual`; vacío si no hay cotización |
| creado_por | uuid | default `auth.uid()` |

**`gastos`**

| Campo | Tipo | Reglas |
|---|---|---|
| obra_id | bigint | FK `obras`, cascade |
| fecha | date | default hoy; no futura |
| rubro_id | bigint | FK `rubros` |
| descripcion | text | no vacía |
| proveedor | text | opcional |
| monto | numeric(14,2) | > 0 |
| moneda | text | `ARS` o `USD` |
| tipo_cambio | numeric(12,4) | ARS por USD (MEP promedio); > 0 o vacío |
| tipo_cambio_origen | text | `auto` o `manual`; vacío si no hay cotización |
| anulado | bool | default `false` |
| creado_por | uuid | default `auth.uid()` |

RLS en las tres tablas: el equipo lee, crea y actualiza (para anular o
corregir la cotización). Sin DELETE.

## Reglas de negocio

- **R1.** Los montos se guardan en su moneda original; nunca se reescriben.
- **R2.** Los gastos anulados no cuentan en ningún total, pero siguen visibles
  como anulados.
- **R3. Cotización automática.** Al guardar un gasto o ítem, en **cualquier
  moneda**, se busca el dólar MEP de su fecha y se guarda el **promedio entre
  compra y venta**, con origen `auto`. Así cualquier monto puede mostrarse en
  ARS o en USD.
  - Si esa fecha no tiene cotización (fin de semana o feriado), se usa la del
    último día hábil anterior.
  - Si el servicio no responde, el gasto **se guarda igual**, sin cotización, y
    la app avisa y ofrece cargarla a mano.
- **R4. Corrección manual.** El usuario puede reemplazar la cotización; queda con
  origen `manual` y no se vuelve a pisar con la automática.
- **R5. Conversión.** Para mostrar en otra moneda se usa la cotización guardada
  en cada gasto o ítem (ARS = USD × tc; USD = ARS ÷ tc). Si un gasto no tiene
  cotización, **no se convierte**: el resumen lo informa aparte y avisa que el
  total está incompleto.
- **R6.** Desvío = gastado − presupuestado. Porcentaje ejecutado =
  gastado ÷ presupuestado. Si un rubro no tiene presupuesto, se muestra
  «sin presupuesto».
- **R7.** Un rubro desactivado no aparece para cargas nuevas, pero sí en los
  datos históricos.

## Técnico

- Las cotizaciones se piden en `atrium/cotizaciones.py`, con la URL de la fuente
  en `Settings`, timeout corto y caché por fecha. Fuente prevista: una API
  pública con histórico del MEP («bolsa»), como ArgentinaDatos; se confirma al
  implementar.
- Los tests nunca llaman a la API real: se simula con un fake que permite probar
  día hábil, fin de semana y servicio caído.

## Pantallas

En la sección **📋 Obras**, una pestaña nueva **💰 Plata**:
1. Selector de obra y de moneda de visualización (ARS / USD MEP).
2. Tres números arriba: presupuestado, gastado y desvío (en rojo si se pasa).
3. Tabla por rubro con barra de ejecución.
4. Botón **+ Gasto** con un formulario corto: monto, moneda, rubro y descripción.
   Plegados quedan fecha, proveedor y cotización (precargada, editable).
5. Últimos gastos con su cotización (✏️ si es manual), con opción de anular.
6. Carga del presupuesto por ítems, en un desplegable.

## Agente

Herramientas nuevas:
- `registrar_gasto(monto, moneda, rubro, descripcion, obra?, fecha?, proveedor?)`
  — solo si se pide. La cotización se completa sola (R3). Si el rubro es ambiguo,
  pregunta.
- `resumen_plata(obra?, moneda?)` — presupuestado, gastado y desvío por rubro.

Ejemplos: «¿cuánto llevamos gastado en Lote 12 en dólares?», «¿en qué rubro nos
estamos pasando?», «cargá 350 mil pesos de hierro, proveedor Hierros Sur».

## Criterios de aceptación

- **F-03-CA-1** — *Dado* una obra sin presupuesto *cuando* cargo ítems en tres
  rubros *entonces* el resumen muestra el presupuesto por rubro y el total.
- **F-03-CA-2** — *Dado* una obra con presupuesto *cuando* registro un gasto
  *entonces* aparece en los últimos gastos y suma en su rubro y en el total.
- **F-03-CA-3** — *Dado* que el MEP de hoy cotiza compra 1190 y venta 1210
  *cuando* registro un gasto con fecha de hoy *entonces* se guarda con
  cotización 1200 y origen `auto`.
- **F-03-CA-4** — *Dado* un gasto con fecha de un sábado *cuando* lo registro
  *entonces* toma la cotización del viernes anterior.
- **F-03-CA-5** — *Dado* que el servicio de cotizaciones no responde *cuando*
  registro un gasto *entonces* se guarda sin cotización, veo un aviso y puedo
  cargarla a mano.
- **F-03-CA-6** — *Dado* un gasto con cotización automática *cuando* la corrijo a
  1180 *entonces* queda con origen `manual`, se muestra con ✏️ y el resumen usa 1180.
- **F-03-CA-7** — *Dado* un gasto de USD 1.000 con cotización 1200 y uno de
  ARS 600.000 con cotización 1200 *cuando* veo el resumen en ARS *entonces* el
  gastado es 1.800.000, y en USD es 1.500.
- **F-03-CA-8** — *Dado* un gasto en USD **sin** cotización *cuando* veo el resumen
  en ARS *entonces* no se suma y aparece un aviso de total incompleto.
- **F-03-CA-9** — *Dado* un gasto cargado *cuando* lo anulo *entonces* deja de
  sumar, se ve tachado y no se borra de la base.
- **F-03-CA-10** — *Dado* un gasto con monto 0 o negativo, sin descripción o con
  fecha futura *cuando* intento guardarlo *entonces* se rechaza con un mensaje
  claro, en la app y en la base.
- **F-03-CA-11** — *Dado* la obra activa Lote 12 *cuando* le pido al agente
  «cargá 350 mil pesos de hierro» *entonces* registra el gasto en Estructura con la
  cotización del día, avisa qué guardó, y aparece en 💰 Plata.
- **F-03-CA-12** — *Dado* gastos y presupuesto cargados *cuando* pregunto «¿en qué
  rubro nos pasamos?» *entonces* el agente responde con los rubros con desvío
  usando datos reales.
- **F-03-CA-13** — *Dado* un usuario sin login *cuando* consulta gastos,
  presupuestos o rubros *entonces* no ve nada (RLS).

## Decisiones

| # | Pregunta | Decisión |
|---|---|---|
| D1 | ¿Moneda del presupuesto? | ✅ Cada ítem en su moneda |
| D2 | ¿De dónde sale el tipo de cambio? | ✅ Automático desde internet, editable a mano (queda registrado el origen) |
| D3 | ¿Qué dólar es la referencia? | ✅ MEP, valor **promedio** entre compra y venta |
| D4 | ¿Lista de rubros? | ✅ La propuesta más **Steel frame** |
| D5 | ¿Ingresos, señas y aportes? | ✅ No en F-03; ficha aparte «Flujo de fondos» |
| D6 | ¿Quién ve gastos y presupuestos? | ✅ Todo el equipo, como las obras |
| D7 | ¿Qué cotización usan los ítems de presupuesto? | ✅ La misma regla que los gastos: MEP promedio de su fecha, editable *(derivada de D2 y D3; confirmar)* |
