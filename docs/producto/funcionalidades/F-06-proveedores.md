# F-06 · Proveedores

**Estado:** Hecha
**Prioridad:** Alta
**Depende de:** F-03 (gastos por ítem, #35), UX-03 (menú, #49) · Issue: #37

## Objetivo

Una **lista de proveedores compartida** por el equipo, reutilizable entre obras:
al cargar un gasto se **elige** el proveedor en vez de escribirlo, se tienen sus
datos de contacto a mano, se ve **cuánto se le compró** en todas las obras y
**qué opinan los socios** (estrellas).

## Historias

- Como **socia**, quiero dar de alta un proveedor con contacto y rubros, para encontrarlo rápido.
- Como **socia**, quiero elegir el proveedor de una lista al cargar un gasto, sin errores de tipeo.
- Como **socia**, quiero ver qué le compramos en cada obra y cuánto, para negociar o decidir a quién llamar.
- Como **socia**, quiero dar de alta un proveedor sin salir del gasto que estoy cargando.
- Como **socia**, quiero calificarlo con estrellas y ver qué opinan mis socios.

## Alcance

**Incluye**
- 🏢 Proveedores (menú, Configuración): lista con búsqueda, filtro por rubro y «Mostrar eliminados»; «+ Nuevo proveedor».
- Ficha: datos, botones Llamar · WhatsApp · Mail · Web, compras por obra y moneda, calificaciones.
- Alta, edición, «Eliminar» (archiva, con confirmación) y «Restaurar».
- Calificaciones: una por socio, de 1 a 5 estrellas con comentario opcional; promedio visible.
- Gastos: el proveedor se elige de la lista, con «+ Nuevo proveedor» (alta rápida) en el mismo formulario.
- Migración: un proveedor por cada nombre escrito en gastos anteriores, con sus gastos vinculados.
- Agente: `buscar_proveedor`, `crear_proveedor` (solo si se pide) y `registrar_gasto` con proveedor de la lista.

**No incluye** (por ahora)
- Unir proveedores duplicados (D8).
- Ofertas por ítem (#36, usará esta lista).
- Adjuntos del proveedor (F-05).
- Pagos o cuenta corriente con el proveedor.

## Datos

| Tabla / columna | Tipo | Reglas |
|---|---|---|
| `proveedores.nombre` | text | 2 a 120 caracteres; único sin importar mayúsculas, tildes ni espacios (`rubro_clave`) |
| `contacto`, `zona` | text | hasta 120 |
| `telefono` | text | números, espacios, `+ - ( )`; 6 a 30 |
| `email` | text | formato de mail |
| `web` | text | solo `https://` |
| `cuit` | text | `NN-NNNNNNNN-N`; la app valida el dígito verificador |
| `notas` | text | hasta 1000 |
| `rubro_ids` | bigint[] | rubros de la lista compartida (lo valida un trigger) |
| `archivado` | boolean | «Eliminar» = archivar; sin DELETE |
| `proveedor_calificaciones` | tabla | `estrellas` 1–5, `comentario` ≤ 500, `autor`, `editado_en`; una por (proveedor, socio); RLS: todos leen, cada uno escribe la suya |
| `gastos.proveedor_id` | bigint FK | opcional; un trigger impide elegir un proveedor eliminado. `gastos.proveedor` (texto) queda como historial |

Todas con RLS para `authenticated`, `creado_por` y permisos por columna.

## Reglas de negocio

- R1. **Eliminar** pide confirmación y archiva: desaparece de la lista y de los gastos nuevos, pero sus gastos lo siguen mostrando («(eliminado)»). Se restaura desde «Mostrar eliminados».
- R1b. **Calificaciones**: cada socio la suya (1 a 5 + comentario), editable; se muestra el promedio con el número y la cantidad. Nadie cambia la de otro (también en la base). Un eliminado no recibe calificaciones nuevas.
- R2. El gasto guarda `proveedor_id`; el proveedor es opcional. Ya no se escribe a mano (D3).
- R3. Compras: por moneda, sin mezclar ARS y USD, solo gastos no anulados.
- R4. Los botones de contacto se arman solo con datos validados: `tel:` y `https://wa.me/` con el número normalizado (+54; WhatsApp con 9), `mailto:` y `https://`. Todo el texto va escapado.
- R5. Nada se ve sin login (RLS + LIVE-28).

## Pantallas

```
Proveedores
[🔎 Buscar ]  Rubro [Todos ▾]   [+ Nuevo proveedor]  ☐ Mostrar eliminados
┌──────────────────────────────────────────────────────────────┐
│ Hierros Sur · ★★★★☆ 4,5 · 2 calificaciones          [Abrir] │
│ Estructura · Juan Pérez · 221 555 1234                       │
│ 5 gastos en 2 obras · ARS 3.450.000                          │
└──────────────────────────────────────────────────────────────┘
Ficha: [✏️ Editar] [🗑️ Eliminar] · datos · [📞][💬][✉️][🌐]
        Compras (total y por obra) · Calificaciones (la mía + todas)
Gasto:  Proveedor [Hierros Sur ▾]  + Nuevo proveedor
```

## Agente

- `buscar_proveedor(texto, rubro)`: contacto, calificación y compras.
- `crear_proveedor(...)`: **Usala SOLO si el usuario pide** darlo de alta o lo confirma.
- `registrar_gasto(..., proveedor)`: si el proveedor no está en la lista, no guarda y pregunta (D6).
- Nunca califica proveedores.

## Criterios de aceptación

- **F-06-CA-1**: alta completa → en la lista y en su ficha con rubros, contacto y botones.
- **F-06-CA-2**: nombre repetido o mail inválido → no guarda, dice por qué, conserva lo escrito.
- **F-06-CA-3**: búsqueda por nombre, contacto o rubro; filtro por rubro.
- **F-06-CA-4**: editar con los datos actuales.
- **F-06-CA-5**: eliminar con confirmación; se puede cancelar; restaurar.
- **F-06-CA-6**: calificar con comentario; promedio y la de cada uno; cambiar la mía. **CA-6b:** sin estrellas no guarda.
- **F-06-CA-7**: compras por obra y moneda, sin anulados.
- **F-06-CA-8**: el gasto elige el proveedor de la lista; se ve en la tabla.
- **F-06-CA-9**: alta rápida desde el gasto, con el rubro del ítem; queda elegido.
- **F-06-CA-10**: un eliminado no se ofrece en gastos nuevos; el gasto viejo lo muestra.
- **F-06-CA-11**: Markdown en nombre, notas o comentario se muestra como texto.
- **F-06-CA-12**: el agente busca un proveedor con datos reales.
- **F-06-CA-13**: el agente no guarda un gasto de un proveedor desconocido y pregunta.
- **F-06-CA-14**: el agente da de alta un proveedor si se lo piden.
- **LIVE-28/29/30**: sin login no se ve; cada socio su calificación; eliminado no se elige.

## Decisiones (Carolina, 23/10/2026)

| # | Pregunta | Decisión |
|---|---|---|
| D1 | Datos | Nombre (obligatorio), rubros, contacto, teléfono, mail, web, CUIT, zona y notas |
| D2 | Calificación | Sí: cada socio 1 a 5 estrellas + comentario; promedio visible |
| D3 | ¿Proveedor a mano en el gasto? | No: de la lista, con alta rápida |
| D4 | Gastos con proveedor escrito | Un proveedor por nombre distinto, gastos vinculados |
| D5 | Historial de compras | Sí, en la ficha, solo lectura |
| D6 | Proveedor que el agente no encuentra | Pregunta antes de darlo de alta |
| D7 | Botones de contacto | Sí |
| D8 | Unir duplicados | Más adelante |
| D9 | Ofertas (#36) | Usarán esta lista |
| D10 | Eliminar | Botón «Eliminar» que archiva, con confirmación; se restaura |
| D11 | Rubros del proveedor | Los de 🏷️ Rubros, la misma lista del presupuesto |
