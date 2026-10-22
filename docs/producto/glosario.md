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
| **Obra activa** | La obra elegida en la barra lateral; le da contexto al agente. | `obra_activa` (sesión) · `obra_id` (estado del grafo) |
| **Normativa** | Códigos de edificación municipales cargados en `docs/` e indexados. | Chroma, colección `obra` |
| **Agente** | El asistente de chat. Responde normativa y lee o escribe obras con herramientas. | `atrium/rag.py` · `atrium/obra_tools.py` |
| **Equipo** | Los usuarios con login. Todos ven y editan todas las obras. | rol `authenticated` en RLS |

## Nuevos (propuestos en las fichas F-03 a F-05)

| Término | Significado | En el código (propuesto) |
|---|---|---|
| **Rubro** | Categoría de trabajo o costo: Fundaciones, Estructura, Mampostería, Instalación eléctrica… Se comparte entre presupuesto y etapas. | tabla `rubros` |
| **Presupuesto** | Lo que se prevé gastar en una obra, desglosado en **ítems** por rubro, con moneda. | tabla `presupuesto_items` |
| **Gasto** | Un pago o compromiso real: fecha, rubro, monto, moneda, proveedor y comprobante opcional. | tabla `gastos` |
| **Desvío** | Diferencia entre lo gastado y lo presupuestado, por rubro y total, en una misma moneda. | calculado en `atrium/finanzas.py` |
| **Tipo de cambio** | Cotización ARS por USD usada para convertir. Siempre explícita y con fecha. | `gastos.tipo_cambio` |
| **Etapa** | Tramo planificado de la obra (por ejemplo «Estructura»), con fechas previstas y reales, y avance propio. | tabla `etapas` |
| **Cronograma** | El conjunto ordenado de etapas de una obra. | vista en `obras_ui.py` |
| **Atraso** | Una etapa cuya fecha de fin prevista ya pasó sin estar terminada, o que va más lenta de lo previsto. | calculado en `atrium/cronograma.py` |
| **Archivo de obra** | Foto o documento adjunto a una obra; opcionalmente ligado a una nota de bitácora, una etapa o un gasto. | tabla `archivos` + Supabase Storage |
| **Tipo de documento** | Foto · Plano · Permiso · Contrato · Comprobante · Otro | `archivos.tipo` |
