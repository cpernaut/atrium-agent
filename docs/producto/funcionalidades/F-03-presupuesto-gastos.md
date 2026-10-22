# F-03 · Presupuesto y gastos

**Estado:** Hecha
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
- Anular un gasto o un ítem de presupuesto mal cargado (no se borra).
- **Rubros nuevos — preparado:** la base y el dominio ya permiten agregar,
  desactivar y reactivar rubros (`finanzas.create_rubro`, `set_rubro_activo`),
  con nombres únicos sin importar mayúsculas, tildes ni espacios. Falta solo la
  pantalla: próxima iteración (ver «Siguiente iteración»).

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
| monto | numeric(14,2) | ≥ 0 (puede valer 0: el precio se carga después, D9) |
| moneda | text | `ARS` o `USD` |
| fecha | date | default hoy; fecha de la cotización |
| es_imprevistos | bool | default `false`; como mucho un «Imprevistos» vigente por obra |
| tipo_cambio | numeric(12,4) | ARS por USD (MEP promedio); > 0 o vacío |
| tipo_cambio_origen | text | `auto` o `manual`; vacío si no hay cotización |
| creado_por | uuid | default `auth.uid()` |

**`gastos`**

| Campo | Tipo | Reglas |
|---|---|---|
| presupuesto_item_id | bigint | FK `presupuesto_items`, **obligatorio**; ítem vigente de la misma obra; no se cambia |
| obra_id | bigint | FK `obras`, cascade; lo pone la base desde el ítem |
| fecha | date | default hoy; no futura |
| rubro_id | bigint | FK `rubros`; lo pone la base desde el ítem y lo sigue si el ítem cambia de rubro |
| descripcion | text | no vacía |
| proveedor | text | opcional |
| monto | numeric(14,2) | > 0 |
| moneda | text | `ARS` o `USD` |
| tipo_cambio | numeric(12,4) | ARS por USD (MEP promedio); > 0 o vacío |
| tipo_cambio_origen | text | `auto` o `manual`; vacío si no hay cotización |
| anulado | bool | default `false` |
| creado_por | uuid | default `auth.uid()` |

RLS en las tres tablas: el equipo lee, crea y actualiza (para anular o
corregir la cotización). Sin DELETE. Triggers: `gastos_desde_item` (obra y rubro
del gasto desde su ítem; rechaza ítems borrados o de otra obra) y
`presupuesto_items_propaga` (si el ítem cambia de rubro o se borra, sus gastos lo
siguen).

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
  gastado ÷ presupuestado. Sin presupuesto no hay porcentaje (ver R16).
- **R7.** Un rubro desactivado no aparece para cargas nuevas, pero sí en los
  datos históricos.
- **R8. Sin valores por defecto que induzcan errores.** Los formularios de alta
  (gasto e ítem de presupuesto) arrancan con el rubro vacío («Elegí un rubro»), y
  el de ítem de presupuesto arranca **completamente vacío**: rubro, descripción,
  monto, moneda y cotización. Guardar sin elegir rubro (o moneda) se rechaza con
  un mensaje claro y el formulario conserva lo escrito. El monto del ítem es
  opcional: vacío se guarda como 0 (D9). En el gasto, la moneda es la excepción:
  arranca en la del ítem (R15).
- **R9. Edición de ítems de presupuesto.** Se pueden cambiar rubro, descripción,
  monto, moneda y cotización. Nunca cambian la obra, la fecha de carga ni quién lo
  cargó (la base lo impide, no solo la app). Si se cambia la cotización, queda con
  origen `manual`. Valen las mismas validaciones que al crear. Un ítem borrado no
  se puede editar.
- **R10. Borrar un ítem de presupuesto = ocultarlo y conservarlo** (decisión
  D8). Pide confirmación en un diálogo que dice qué ítem se borra y qué efecto
  tiene; al confirmar, el ítem desaparece de la lista y de los totales, pero queda
  en la base como `anulado`. Cancelar o cerrar el diálogo no cambia nada.

**Gastos por ítem** (issue #35, decisiones D9 a D16)

- **R11. Todo gasto pertenece a un ítem** de presupuesto vigente de la misma obra.
  El rubro y la obra del gasto los toma del ítem (la base lo garantiza). Ningún
  gasto queda suelto: no hay formulario de gasto fuera de un ítem.
- **R12. «Imprevistos».** Toda obra nueva nace con un ítem «Imprevistos» en el
  rubro **Otros**, en la **moneda de la obra**, por el **10 % del presupuesto de
  la obra** (0 si no tiene). Se calcula una vez, al crearlo. Se puede editar,
  poner en 0 o borrar como cualquier ítem; si no hay uno vigente, el alta de ítem
  ofrece «Es el ítem de imprevistos». Ahí van los gastos que no tienen otro ítem.
  Las obras que ya existían lo reciben con la migración.
- **R12b. Borrar un ítem con gastos** borra (anula) el ítem **y sus gastos**. El
  diálogo avisa cuántos gastos tiene y por qué monto, y el botón dice «Borrar ítem
  y gastos».
- **R13.** Un gasto puede estar en otra moneda que su ítem; para comparar se usa
  la cotización de cada uno. Sin cotización, el ítem avisa «total incompleto».
- **R14. Anular un gasto** pide confirmación en un diálogo que lo nombra; deja de
  sumar y queda tachado y guardado.
- **R15.** Al agregar un gasto, la moneda arranca en la del ítem y se puede
  cambiar. Los demás campos arrancan vacíos (la fecha, en hoy).
- **R16. Semáforo.** Cada ítem muestra total, gastado y % consumido. Estado:
  🟢 **Dentro del presupuesto** (< 90 %), 🟡 **Cerca del límite** (90 % a 100 %,
  inclusive), 🔴 **Excedido** (> 100 %). Sin presupuesto: 🔴 «Excedido» si tiene
  gastos, ⚪ «Sin presupuesto asignado» si no. El mismo criterio vale para
  rubros y el total de la obra, y siempre se escribe en palabras.

## Técnico

- Las cotizaciones se piden en `atrium/cotizaciones.py`, con la URL de la fuente
  en `Settings`, timeout corto y caché por fecha. Fuente prevista: una API
  pública con histórico del MEP («bolsa»), como ArgentinaDatos; se confirma al
  implementar.
- Los tests nunca llaman a la API real: se simula con un fake que permite probar
  día hábil, fin de semana y servicio caído.

## Pantallas

En la sección **📋 Obras**, la pestaña **💰 Plata**:
1. Selector de obra y de moneda de visualización (ARS / USD MEP).
2. Tres números arriba: presupuestado, gastado y desvío, con el estado en palabras.
3. Tabla por rubro con barra de ejecución.
4. **Presupuesto de la obra** (sección visible, no plegada):
   - Lista de ítems **agrupada por rubro**, en el orden de obra. Cada grupo muestra
     el rubro, la cantidad de ítems, el subtotal, lo gastado y el estado.
   - Cada ítem es una fila desplegable titulada con descripción, total, gastado,
     % consumido y estado (R16). Al abrirla se ve primero el **resumen** (total,
     gastado, saldo, estado y barra), después los **detalles** (rubro, descripción,
     fecha de carga, cotización) y las acciones **Editar ítem** y **Borrar ítem**.
   - Debajo, **Gastos de este ítem**: fecha, monto, descripción, proveedor y
     cotización de cada uno, con **Cotización** (corregirla a mano) y **Anular**.
     Los anulados se ven tachados y con la palabra «Anulado».
   - **+ Agregar gasto** abre, dentro del ítem, el formulario «Nuevo gasto en
     «…»»: fecha, monto, moneda (la del ítem), descripción, proveedor y
     cotización opcional, con **Agregar gasto** y **Cancelar**.
   - **Editar ítem** reemplaza el ítem por un formulario con los valores actuales
     y **Guardar cambios** y **Cancelar**.
   - **Borrar ítem** abre el diálogo de confirmación (R10, R12b).
   - **+ Agregar ítem** abre el formulario de alta **vacío** (R8), con **Agregar**
     y **Cancelar**.

## Agente

Herramientas nuevas:
- `registrar_gasto(monto, descripcion, item, moneda?, rubro?, obra?, fecha?, proveedor?)`
  — solo si se pide. Busca el **ítem** de la obra por su descripción (o por el
  rubro); si hay uno, registra; si hay varios, no guarda y pregunta; si no hay
  ninguno, no guarda y pregunta a qué ítem va o si va a «Imprevistos». Nunca crea
  ítems. Moneda vacía = la del ítem. La cotización se completa sola (R3).
- `resumen_plata(obra?, moneda?)` — presupuestado, gastado y desvío por rubro, y
  total, gastado, saldo y estado por ítem.

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

**Presupuesto: lista, detalle, edición y borrado** (issue #9)

- **F-03-CA-14** — *Dado* ítems en tres rubros *cuando* abro 💰 Plata *entonces*
  veo la lista agrupada por rubro, en orden de obra, con cantidad de ítems y
  subtotal de cada rubro.
- **F-03-CA-15** — *Dado* un ítem *cuando* abro su fila *entonces* veo rubro,
  descripción, monto, moneda, fecha de carga y cotización con su origen, y las
  acciones Editar y Borrar.
- **F-03-CA-16** — *Dado* que toco «+ Agregar ítem» *entonces* el formulario aparece
  vacío; *y* después de guardar un ítem, al volver a abrirlo, aparece vacío otra vez.
- **F-03-CA-17** — *Dado* el alta sin rubro o sin moneda *cuando* toco Agregar
  *entonces* veo «Elegí un rubro» (o la moneda), no se guarda nada y lo escrito se
  conserva.
- **F-03-CA-18** — *Dado* un ítem *cuando* toco Editar *entonces* aparece el
  formulario con sus valores actuales, con Guardar cambios y Cancelar.
- **F-03-CA-19** — *Dado* un ítem en edición *cuando* cambio monto y rubro y
  guardo *entonces* el ítem y los subtotales se actualizan y el formulario se cierra.
- **F-03-CA-20** — *Dado* un ítem en edición con cambios *cuando* toco Cancelar
  *entonces* no se guarda nada y vuelvo a ver los detalles originales.
- **F-03-CA-21** — *Dado* un ítem en edición *cuando* guardo un monto inválido
  *entonces* veo el error, no se guarda y el formulario conserva lo escrito.
- **F-03-CA-22** — *Dado* un ítem *cuando* toco Borrar *entonces* aparece un
  diálogo que nombra el ítem y pide confirmación; *si* cancelo, no cambia nada;
  *si* confirmo, desaparece de la lista y de los totales y queda anulado en la base.
- **F-03-CA-23** — *Dado* un ítem con texto que contiene Markdown *cuando* veo la
  lista, el detalle, el formulario o el diálogo *entonces* el texto se muestra tal
  cual, sin interpretarse.
- **F-03-CA-24** — *Dado* un usuario logueado *cuando* intenta, salteando la app,
  cambiar la obra, la fecha de carga o el autor de un ítem *entonces* la base lo
  rechaza.
- **F-03-CA-25** — *(reemplazado por CA-27 y CA-32: ya no hay gasto suelto.)*

**Gastos por ítem** (issue #35). Los CA-2, CA-9, CA-10 y CA-11 se cumplen ahora
dentro de cada ítem (CA-27, CA-29, CA-28 y CA-33).

- **F-03-CA-26** — *Dado* un ítem de ARS 100.000 *cuando* sus gastos suman 89.000,
  90.000, 100.000 o 101.000 *entonces* veo total, gastado y %, con
  🟢 «Dentro del presupuesto», 🟡 «Cerca del límite», 🟡 «Cerca del límite» y
  🔴 «Excedido»; al abrirlo veo sus gastos y el saldo.
- **F-03-CA-27** — *Dado* un ítem *cuando* toco «+ Agregar gasto» *entonces* se abre
  dentro del ítem un formulario vacío que lo nombra, con la moneda del ítem
  precargada (se puede cambiar); al guardar, el gasto aparece en ese ítem y se
  actualizan el ítem, el rubro y los totales.
- **F-03-CA-28** — *Dado* el formulario de gasto sin monto o sin descripción
  *cuando* toco Agregar gasto *entonces* dice qué falta, no guarda y conserva lo
  escrito.
- **F-03-CA-29** — *Dado* un gasto *cuando* toco Anular *entonces* un diálogo lo
  nombra; *si* cancelo, no cambia nada; *si* confirmo, se ve tachado («Anulado»),
  deja de sumar y sigue en la base.
- **F-03-CA-30** — *Dado* un ítem con gastos *cuando* toco Borrar ítem *entonces* el
  diálogo avisa cuántos gastos tiene y por qué monto; confirmar anula el ítem y
  sus gastos, que siguen en la base y dejan de sumar.
- **F-03-CA-30b** — *Dado* que creo una obra con presupuesto USD 85.000 *entonces*
  ya tiene «Imprevistos» por USD 8.500 en Otros; sin presupuesto, por 0.
- **F-03-CA-30c** — *Dado* una obra sin «Imprevistos» vigente *cuando* agrego un
  ítem *entonces* puedo marcarlo como imprevistos; si ya hay uno, no se ofrece.
- **F-03-CA-30d** — *Dado* el alta de ítem sin monto *cuando* lo agrego *entonces* se
  guarda en 0 y muestra «Sin presupuesto asignado»; un negativo se rechaza.
- **F-03-CA-31** — *Dado* un gasto en USD en un ítem en ARS *entonces* se convierte
  con la cotización del gasto; sin cotización, el ítem dice «total incompleto».
- **F-03-CA-32** — Ya no existe un formulario de gasto suelto ni «Últimos gastos».
- **F-03-CA-33** — *Dado* «cargá 350 mil de hierro» por chat *cuando* un solo ítem
  coincide *entonces* registra el gasto en ese ítem; con varios, no guarda y
  pregunta; con ninguno, no guarda y ofrece «Imprevistos».
- **F-03-CA-34** — *Dado* un usuario logueado *cuando* intenta, salteando la app,
  crear un gasto sin ítem, con un ítem de otra obra o borrado, o mover un gasto de
  ítem *entonces* la base lo rechaza; obra y rubro del gasto siempre son los del
  ítem.
- **F-03-CA-35** — *Dado* un ítem con gastos *cuando* le cambio el rubro *entonces*
  sus gastos pasan a ese rubro en el resumen.

## Implementación

| Pieza | Dónde |
|---|---|
| Tablas, precarga, restricciones y RLS | `supabase_schema.sql` |
| Cotización MEP | `atrium/cotizaciones.py` (fuente: ArgentinaDatos, serie `bolsa`, caché de 1 hora) |
| Reglas y cálculos | `atrium/finanzas.py` |
| Pantalla 💰 Plata | `plata_ui.py` |
| Herramientas del agente | `registrar_gasto`, `resumen_plata` en `atrium/obra_tools.py` |
| «Imprevistos» de una obra nueva | `obras_ui.py` → `finanzas.crear_imprevistos` |
| Tests | `tests/test_finanzas.py`, `tests/test_cotizaciones.py`, `tests/e2e/test_plata_flows.py`, `tests/e2e/test_presupuesto_flows.py`, `tests/live/test_finanzas_live.py`, `tests/sql/test_rls_f03.sql` |

**Seguridad:** RLS en las tres tablas, sin DELETE; todas las reglas de datos
también como `check` en la base; la URL de cotizaciones es fija y su respuesta se
valida (tamaño, formato y números); el texto que cargan los usuarios se escapa
antes de mostrarlo, así no puede insertar links ni imágenes externas.

**Accesibilidad:** todos los campos con etiqueta visible y los obligatorios lo
dicen; el estado del desvío se escribe en palabras (no solo color); anulados
tachados **y** con la palabra «Anulado»; montos con formato argentino y su
moneda; si hay un error, el formulario conserva lo escrito; anular pide
confirmación explícita.

## Siguiente iteración

- **Pantalla de rubros:** agregar, renombrar, ordenar y desactivar rubros desde
  la app. El dominio y la base ya lo soportan.
- Editar un gasto, incluido moverlo a otro ítem (#25; hoy se anula y se carga de
  nuevo).
- Varias ofertas de proveedores por ítem (#36) y lista de proveedores (#37).

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
| D8 | ¿Qué hace «Borrar» en un ítem de presupuesto? | ✅ Lo oculta de la lista y de los totales, pero lo conserva en la base como anulado (22/10/2026) |
| D9 | ¿Un ítem puede valer 0? | ✅ Sí, cualquiera: se listan los ítems y los montos se cargan después. Vacío = 0 (#35) |
| D10 | ¿Gasto imprevisto sin ítem? | ✅ Ítem «Imprevistos» por defecto en cada obra; ningún gasto queda suelto (#35) |
| D11 | ¿Borrar un ítem con gastos? | ✅ Sí: se borran el ítem y sus gastos; la confirmación lo avisa (#35) |
| D12 | ¿Moneda del gasto nuevo? | ✅ La del ítem, editable (#35) |
| D13 | ¿Qué muestra cada ítem? | ✅ Total, gastado y %; rojo > 100 %, amarillo 90–100 %, verde < 90 % (#35) |
| D14 | ¿Mover un gasto a otro ítem? | ✅ Sí, a futuro, con «Editar gasto» (#25) |
| D15 | ¿Monto inicial de «Imprevistos»? | ✅ 10 % del presupuesto de la obra; puede valer 0; editable y borrable (#35) |
| D16 | ¿Moneda de «Imprevistos»? | ✅ La de la obra (#35) |
