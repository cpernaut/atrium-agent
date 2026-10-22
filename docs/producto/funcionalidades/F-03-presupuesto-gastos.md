# F-03 · Presupuesto y gastos

**Estado:** Borrador
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
- Como **socio**, quiero ver gastado contra presupuestado por rubro para
  detectar desvíos a tiempo.
- Como **socio**, quiero decirle al agente «cargá un gasto de 350 mil pesos
  en hierro para Lote 12» y que quede registrado.

## Alcance

**Incluye**
- Lista de **rubros** común a todas las obras, precargada y ampliable.
- Ítems de presupuesto por obra: rubro, descripción, monto y moneda.
- Gastos: fecha, rubro, descripción, proveedor, monto, moneda y, si hace falta,
  tipo de cambio.
- Resumen por obra: presupuestado, gastado, desvío y porcentaje ejecutado,
  por rubro y total, en una **moneda de visualización** elegida.
- Herramientas del agente para cargar gastos y consultar el resumen.
- Anular un gasto mal cargado (no se borra).

**No incluye** (por ahora)
- Comprobantes adjuntos (llega con F-05, ligado al gasto).
- Cotizaciones automáticas del dólar desde internet.
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

Precarga sugerida: Trabajos preliminares · Movimiento de suelo · Fundaciones ·
Estructura · Mampostería · Cubierta · Instalación sanitaria · Instalación
eléctrica · Instalación de gas · Revoques · Contrapisos y carpetas · Pisos y
revestimientos · Carpinterías · Pintura · Honorarios y trámites · Limpieza final · Otros.

**`presupuesto_items`**

| Campo | Tipo | Reglas |
|---|---|---|
| obra_id | bigint | FK `obras`, cascade |
| rubro_id | bigint | FK `rubros` |
| descripcion | text | opcional |
| monto | numeric(14,2) | > 0 |
| moneda | text | `ARS` o `USD` |
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
| tipo_cambio | numeric(12,4) | ARS por USD; ver R3 |
| anulado | bool | default `false` |
| creado_por | uuid | default `auth.uid()` |

RLS: el equipo lee, crea y actualiza (para anular). Sin DELETE.

## Reglas de negocio

- **R1.** Los montos se guardan en su moneda original; nunca se reescriben.
- **R2.** Los gastos anulados no cuentan en ningún total, pero siguen visibles
  como anulados.
- **R3.** Para mostrar un total en una moneda distinta de la original se usa el
  `tipo_cambio` del gasto. Si un gasto no lo tiene, **no se convierte**: el
  resumen lo informa aparte y avisa que el total está incompleto.
- **R4.** Desvío = gastado − presupuestado. Porcentaje ejecutado =
  gastado ÷ presupuestado. Si no hay presupuesto en un rubro, el porcentaje
  se muestra como «sin presupuesto».
- **R5.** Un rubro desactivado no aparece para cargas nuevas, pero sí en los
  datos históricos.

## Pantallas

En la sección **📋 Obras**, una pestaña nueva **💰 Plata**:
1. Selector de obra y de moneda de visualización.
2. Tres números arriba: presupuestado, gastado, desvío (rojo si es negativo).
3. Tabla por rubro con barra de ejecución.
4. Botón **+ Gasto** con un formulario corto (monto, moneda, rubro,
   descripción; lo demás opcional, plegado).
5. Últimos gastos, con opción de anular.
6. Carga del presupuesto por ítems, en un desplegable.

## Agente

Herramientas nuevas:
- `registrar_gasto(monto, moneda, rubro, descripcion, obra?, fecha?, proveedor?, tipo_cambio?)`
  — solo si se pide; si el rubro es ambiguo, pregunta.
- `resumen_plata(obra?, moneda?)` — presupuestado, gastado y desvío por rubro.

Ejemplos: «¿cuánto llevamos gastado en Lote 12?», «¿en qué rubro nos estamos
pasando?», «cargá 350 mil pesos de hierro, proveedor Hierros Sur».

## Criterios de aceptación

- **F-03-CA-1** — *Dado* una obra sin presupuesto *cuando* cargo ítems en tres
  rubros *entonces* el resumen muestra el presupuesto por rubro y el total.
- **F-03-CA-2** — *Dado* una obra con presupuesto *cuando* registro un gasto
  *entonces* aparece en los últimos gastos y suma en su rubro y en el total.
- **F-03-CA-3** — *Dado* un gasto en USD con tipo de cambio 1200 *cuando* veo el
  resumen en ARS *entonces* ese gasto cuenta como monto × 1200.
- **F-03-CA-4** — *Dado* un gasto en USD **sin** tipo de cambio *cuando* veo el
  resumen en ARS *entonces* no se suma y aparece un aviso de total incompleto.
- **F-03-CA-5** — *Dado* un gasto cargado *cuando* lo anulo *entonces* deja de
  sumar, se ve tachado y no se borra de la base.
- **F-03-CA-6** — *Dado* un gasto con monto 0, negativo o sin descripción
  *cuando* intento guardarlo *entonces* se rechaza con un mensaje claro, en la
  app y en la base.
- **F-03-CA-7** — *Dado* la obra activa Lote 12 *cuando* le pido al agente
  «cargá 350 mil pesos de hierro» *entonces* registra el gasto en Estructura,
  avisa qué guardó, y aparece en 💰 Plata.
- **F-03-CA-8** — *Dado* gastos y presupuesto cargados *cuando* pregunto «¿en qué
  rubro nos pasamos?» *entonces* el agente responde con los rubros con desvío
  negativo usando datos reales.
- **F-03-CA-9** — *Dado* un usuario sin login *cuando* consulta gastos o
  presupuestos *entonces* no ve nada (RLS).

## Decisiones pendientes

| # | Pregunta | Recomendación | Decisión |
|---|---|---|---|
| D1 | ¿El presupuesto de una obra tiene una sola moneda o cada ítem la suya? | Cada ítem la suya, como en la realidad (materiales en ARS, honorarios en USD). | ⏳ |
| D2 | ¿Qué tipo de cambio se usa por defecto al cargar un gasto en otra moneda? | Ninguno automático: se carga a mano cuando hace falta (R3). Más adelante, sugerir el último usado. | ⏳ |
| D3 | ¿Qué dólar es la referencia: oficial, MEP o blue? | No elegir uno en el sistema: el tipo de cambio es el que realmente se usó en cada operación. | ⏳ |
| D4 | ¿La lista de rubros sugerida te sirve? ¿Agregás o sacás alguno? | Usar la precarga y ajustarla con el uso. | ⏳ |
| D5 | ¿Se registran también ingresos (ventas, señas, aportes de socios)? | No en F-03. Si importa para el flipping, ficha aparte «Flujo de fondos». | ⏳ |
| D6 | ¿Los gastos los ve todo el equipo, igual que las obras? | Sí, mismo criterio de equipo que F-02. | ⏳ |
