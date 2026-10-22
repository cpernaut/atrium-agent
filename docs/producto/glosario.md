# Glosario

Un término = un significado = un nombre en el código. Si aparece un término
nuevo, se agrega acá antes de usarlo en el código.

Convención: el código (funciones, módulos, docstrings) está en inglés, pero
**los nombres del dominio van en español** tal como figuran en la columna
«En el código» (tablas, columnas, valores y textos de la interfaz).

## Ya existen

| Término | Significado | En el código |
|---|---|---|
| **Obra** | Un trabajo de arquitectura o construcción con dirección, cliente y municipio. Es la unidad central. | tabla `obras` |
| **Municipio** | Partido donde está la obra. Define qué código de edificación aplica. | `obras.municipio` · `NORMATIVA_POR_MUNICIPIO` |
| **Estado de obra** | Planificación · En curso · Pausada · Terminada · Cancelada | `obras.estado` · `ESTADOS` |
| **Avance** | Porcentaje físico de la obra, de 0 a 100. | `obras.avance` |
| **Bitácora** | Registro cronológico de lo que pasa en la obra. Cada entrada es una **nota**. | tabla `bitacora` |
| **Obra elegida** | La obra que se elige arriba de la pantalla: la usan todas las pestañas y el agente. Por defecto, la última usada o la En curso más nueva. | `obra_elegida` (sesión) · `obras.obra_por_defecto` · `obra_id` (estado del grafo) |
| **Normativa** | Códigos de edificación municipales cargados en `docs/` e indexados. | Chroma, colección `obra` |
| **Agente** | El asistente de chat. Responde normativa y lee o escribe obras con herramientas. | `atrium/rag.py` · `atrium/obra_tools.py` |
| **Equipo** | Los usuarios con login. Todos ven y editan todas las obras. | rol `authenticated` en RLS |

## Presupuesto y gastos (F-03)

| Término | Significado | En el código |
|---|---|---|
| **Rubro** | Categoría de trabajo o costo: Fundaciones, Estructura, Steel frame… Lista compartida, precargada y ampliable; se desactiva en vez de borrarse. Se comparte entre presupuesto y etapas. | tabla `rubros` · `RUBROS_INICIALES` |
| **Presupuesto** | Lo que se prevé gastar en una obra, desglosado en **ítems** por rubro, cada uno con su moneda. | tabla `presupuesto_items` |
| **Ítem (del presupuesto)** | Una línea del presupuesto: rubro, descripción, monto (puede ser 0) y moneda. Los gastos se cargan dentro de su ítem. | `presupuesto_items` · `FilaItem` |
| **Gasto** | Un pago real de un **ítem** del presupuesto: fecha, descripción, monto, moneda y proveedor opcional. El rubro y la obra son los del ítem. | tabla `gastos` · `presupuesto_item_id` |
| **Imprevistos** | El ítem por defecto de cada obra (rubro Otros, 10 % del presupuesto de la obra) para los gastos que no tienen otro ítem. | `es_imprevistos` · `crear_imprevistos` |
| **Saldo** | Total del ítem − gastado. | `FilaItem.saldo` |
| **Semáforo** | Estado de un ítem, rubro u obra según el % consumido: Dentro del presupuesto (< 90 %) · Cerca del límite (90–100 %) · Excedido (> 100 %) · Sin presupuesto asignado. | `finanzas.estado` · `estado_con_icono` |
| **Anular** | Marcar un gasto o ítem como mal cargado: deja de sumar pero no se borra. | columna `anulado` |
| **Borrar (ítem de presupuesto)** | Lo que el usuario ve como «Borrar ítem»: el ítem y sus gastos salen de la lista y de los totales, y quedan anulados en la base (F-03 R10, R12b). | `borrar_presupuesto_item` |
| **Desvío** | Gastado − presupuestado, por rubro y total, en una misma moneda. Positivo = **Excedido**. | `FilaResumen.desvio` · `estado_desvio` |
| **Ejecutado** | Gastado ÷ presupuestado. | `FilaResumen.ejecutado` |
| **Tipo de cambio** | Pesos por dólar usados para convertir: el **MEP promedio** (compra + venta ÷ 2) de la fecha del gasto o ítem. Se trae solo y se puede corregir. | `tipo_cambio` · `tipo_cambio_origen` (`auto`/`manual`) |
| **Cotización** | El valor del MEP de una fecha (o del día hábil anterior), de una fuente pública. | `atrium/cotizaciones.py` |
| **Total incompleto** | Resumen al que le faltan registros que no se pudieron convertir por no tener cotización. | `Resumen.incompleto` |

## Nuevos (propuestos en F-04 y F-05)

| Término | Significado | En el código (propuesto) |
|---|---|---|
| **Etapa** | Tramo planificado de la obra (por ejemplo «Estructura»), con fechas previstas y reales, y avance propio. | tabla `etapas` |
| **Cronograma** | El conjunto ordenado de etapas de una obra. | vista en `obras_ui.py` |
| **Atraso** | Una etapa cuya fecha de fin prevista ya pasó sin estar terminada, o que va más lenta de lo previsto. | calculado en `atrium/cronograma.py` |
| **Archivo de obra** | Foto o documento adjunto a una obra; opcionalmente ligado a una nota de bitácora, una etapa o un gasto. | tabla `archivos` + Supabase Storage |
| **Tipo de documento** | Foto · Plano · Permiso · Contrato · Comprobante · Otro | `archivos.tipo` |
