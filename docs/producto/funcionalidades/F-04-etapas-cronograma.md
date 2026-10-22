# F-04 · Etapas y cronograma

**Estado:** Borrador
**Prioridad:** Alta
**Depende de:** F-02, F-03 (comparte la lista de rubros)

## Objetivo

Planificar cada obra en etapas con fechas, seguir su avance real y detectar
atrasos antes de que sean un problema.

## Historias

- Como **socio**, quiero armar las etapas de una obra con fechas previstas
  para tener un plan.
- Como **socio**, quiero marcar el avance de cada etapa desde la obra para que
  el plan refleje la realidad.
- Como **socio**, quiero ver qué etapas están atrasadas en todas las obras de
  un vistazo.
- Como **socio**, quiero preguntarle al agente «¿qué está atrasado?» o pedirle
  «terminamos la estructura en Lote 12».

## Alcance

**Incluye**
- Etapas por obra: nombre, rubro opcional, orden, fechas de inicio y fin
  previstas y reales, avance (%) y estado.
- **Plantilla de etapas** para crear el cronograma de una obra nueva de un toque.
- Vista de cronograma por obra: lista ordenada con barra de avance y marca
  de atraso; diagrama de Gantt simple si entra en la pantalla.
- Vista **«Atrasos»** con las etapas atrasadas de todas las obras.
- Avance de la obra calculado desde sus etapas (ver D1).
- Herramientas del agente para consultar y actualizar etapas.

**No incluye** (por ahora)
- Dependencias entre etapas ni camino crítico.
- Asignar personas o contratistas a una etapa.
- Recordatorios o notificaciones automáticas.
- Reprogramar todo el cronograma cuando una etapa se atrasa.

## Datos

**`etapas`**

| Campo | Tipo | Reglas |
|---|---|---|
| obra_id | bigint | FK `obras`, cascade |
| nombre | text | no vacío |
| rubro_id | bigint | FK `rubros`, opcional |
| orden | int | define el orden en el cronograma |
| inicio_previsto, fin_previsto | date | fin ≥ inicio |
| inicio_real, fin_real | date | opcionales; fin ≥ inicio |
| avance | int | 0–100 |
| estado | text | Pendiente · En curso · Terminada |
| creado_por | uuid | default `auth.uid()` |

RLS: el equipo lee, crea y actualiza. Sin DELETE (ver D4).

## Reglas de negocio

- **R1.** Al pasar el avance a 100, la etapa queda `Terminada` y, si falta,
  `fin_real` = hoy. Al pasar de 0 a más, queda `En curso` e `inicio_real` = hoy.
- **R2.** Una etapa está **atrasada** si no está terminada y hoy > `fin_previsto`,
  **o** si su avance es menor que el esperado por tiempo transcurrido menos
  un margen (ver D3).
- **R3.** Si la obra tiene etapas, su avance se calcula según D1 y no se edita a
  mano; si no tiene, se mantiene el avance manual de F-02.
- **R4.** Una obra `Terminada` no muestra atrasos.

## Pantallas

En **📋 Obras**, pestaña nueva **📅 Cronograma**:
1. Selector de obra. Si no tiene etapas: botón **Crear desde plantilla**.
2. Lista de etapas en orden: nombre, fechas, barra de avance y 🔴 si hay atraso.
3. Tocar una etapa abre un formulario corto para avance, fechas reales y estado.
4. Arriba de todo, un aviso con la cantidad de etapas atrasadas en todas las obras,
   que lleva a la vista de **Atrasos**.

## Agente

Herramientas nuevas:
- `ver_cronograma(obra?)` — etapas con fechas, avance y atrasos.
- `actualizar_etapa(etapa, obra?, avance?, estado?, fecha?)` — solo si se pide.
- `listar_atrasos()` — etapas atrasadas de todas las obras.

Ejemplos: «¿qué está atrasado?», «terminamos la estructura en Lote 12»,
«¿cuándo arranca la cubierta en Hudson?».

## Criterios de aceptación

- **F-04-CA-1** — *Dado* una obra sin etapas *cuando* toco «Crear desde
  plantilla» *entonces* se crean las etapas de la plantilla en orden, en 0%.
- **F-04-CA-2** — *Dado* una etapa en 0% *cuando* le pongo 30% *entonces* pasa a
  `En curso` con inicio real hoy.
- **F-04-CA-3** — *Dado* una etapa en curso *cuando* le pongo 100% *entonces* pasa
  a `Terminada` con fin real hoy.
- **F-04-CA-4** — *Dado* una etapa no terminada con fin previsto ayer *cuando*
  abro el cronograma *entonces* aparece marcada como atrasada y figura en la vista
  de Atrasos.
- **F-04-CA-5** — *Dado* una obra con etapas *cuando* cambio el avance de una
  etapa *entonces* el avance de la obra se recalcula según D1 y se ve en el listado.
- **F-04-CA-6** — *Dado* fechas con fin anterior al inicio *cuando* guardo
  *entonces* se rechaza con un mensaje claro, en la app y en la base.
- **F-04-CA-7** — *Dado* la obra activa Lote 12 *cuando* le digo al agente
  «terminamos la estructura» *entonces* marca esa etapa al 100%, avisa qué guardó,
  y el cronograma lo refleja.
- **F-04-CA-8** — *Dado* etapas atrasadas en dos obras *cuando* pregunto «¿qué está
  atrasado?» *entonces* el agente lista esas etapas con su obra y días de atraso.
- **F-04-CA-9** — *Dado* una obra `Terminada` con etapas vencidas *cuando* abro
  Atrasos *entonces* esa obra no aparece.

## Decisiones pendientes

| # | Pregunta | Recomendación | Decisión |
|---|---|---|---|
| D1 | ¿Cómo se calcula el avance de la obra desde las etapas? | Promedio ponderado por presupuesto del rubro de cada etapa si existe (F-03); si no, promedio simple. | ⏳ |
| D2 | ¿Qué etapas trae la plantilla? ¿Una sola o según tipo de obra (vivienda, reforma, steel frame)? | Una plantilla por tipo de obra, empezando por Vivienda y Reforma; vos me pasás las etapas. | ⏳ |
| D3 | ¿Se considera atraso solo por fecha vencida, o también por ir lento? | Arrancar solo por fecha vencida (simple y sin falsos positivos); sumar «va lento» más adelante. | ⏳ |
| D4 | ¿Se pueden borrar etapas? | Sí, pero solo si están en 0% y sin fechas reales; el resto se marca como «No aplica». | ⏳ |
| D5 | ¿El Gantt es necesario o alcanza la lista con barras? | Alcanza con la lista en celular; Gantt solo en pantallas anchas. | ⏳ |
