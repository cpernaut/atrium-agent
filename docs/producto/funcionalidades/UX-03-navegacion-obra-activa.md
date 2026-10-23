# UX-03 · Menú a la izquierda y obra activa siempre visible

**Estado:** Hecha
**Prioridad:** Alta
**Depende de:** F-02, F-03, UX-02 (#7) · Issue: #49 · Cubre #6 (UX-01) y #34

## Objetivo

Hoy todo vive en pestañas de una sola pantalla y la obra se elige arriba. Con
más pantallas (rubros, proveedores) eso no escala. UX-03 ordena la app como un
estudio la usa: un **menú a la izquierda** con la **obra activa** y las
pantallas. La obra activa queda **siempre a la vista**, y al elegirla se ve su
**detalle editable**, su bitácora y su presupuesto.

## Historias

- Como **socio de Atrium**, quiero elegir la obra una vez en el menú y verla
  siempre arriba, para saber sobre qué estoy cargando datos.
- Como **socio**, quiero corregir cualquier dato de la obra (cliente, dirección,
  municipio, fechas, presupuesto) sin pedírselo a nadie.
- Como **socio**, quiero que al volver a entrar, aunque sea desde el celular, me
  aparezca la última obra en la que trabajé.
- Como **socio**, quiero administrar la lista de rubros (agregar, ordenar y
  desactivar) desde su propia pantalla.

## Alcance

**Incluye**
- Menú a la izquierda: selector de **obra activa** arriba; debajo, las pantallas
  🏗️ Obra activa, 📋 Obras, ➕ Nueva obra (sección «Obra») y 🏷️ Rubros,
  🏢 Proveedores (sección «Configuración»); al pie, la cuenta.
- Encabezado fijo arriba con la obra activa (nombre, estado y avance), en todas
  las pantallas.
- 🏗️ Obra activa con tres pestañas: **Detalle** (editable), **Bitácora** y
  **Presupuesto** (la ex «💰 Plata»).
- 📋 Obras: métricas, filtro por estado y una tarjeta por obra con «Abrir».
- La obra activa se recuerda por usuario, entre sesiones y dispositivos.
- 🏷️ Rubros: agregar, subir o bajar, desactivar y reactivar.
- 🏢 Proveedores: aviso «Próximamente».

**No incluye** (por ahora)
- Archivar o eliminar obras (#26).
- Lista de proveedores (#37).
- Renombrar rubros.
- Que el menú se cierre solo en el celular al elegir una pantalla (Streamlit no
  lo permite; se cierra con «‹‹»).

## Datos

Sin tablas nuevas.

| Dónde | Qué | Reglas |
|---|---|---|
| Metadatos del usuario (Supabase Auth) | `obra_activa` (id de la obra) | Lo escribe solo el propio usuario. Se trata como dato no confiable: si no es un id válido o la obra no existe, se ignora. |
| `obras` | permisos por columna | Se editan los datos del alta. `id`, `creado_por` y `created_at` no. Nombre no vacío y presupuesto ≥ 0, también en la base. |
| `rubros` | permisos por columna + trigger | Se editan solo `orden` y `activo`. «Otros» no se puede desactivar. |

## Reglas de negocio

- R1. Hay **una** obra activa para toda la app y el agente (sigue UX-02).
- R2. Al entrar, la obra activa es la última que eligió el usuario. Si ya no
  existe, es la En curso más nueva, nunca una Terminada o Cancelada si hay otra.
- R3. La obra activa se guarda en la cuenta solo cuando cambia. Si falla, la app
  sigue andando con la obra elegida.
- R4. Detalle guarda **solo lo que el usuario cambió** respecto de los valores
  con que se abrió el formulario: así no pisa lo que otro (o el agente) cambió
  mientras tanto.
- R5. Cambiar el presupuesto de la obra **no** recalcula «Imprevistos» (D5).
- R6. Cambiar el municipio cambia la normativa que usa el agente (D6).
- R7. Sin obras cargadas, la app abre en «Nueva obra» con un mensaje de
  bienvenida (D8). Una obra nueva queda como obra activa.

## Pantallas

```
┌──────────────────────┬──────────────────────────────────────────┐
│ ⚗ Versión beta       │ 🏗️ Palmeras 55 · En curso · 30 % de avance│ ← fijo
│ Obra activa [▾]      ├──────────────────────────────────────────┤
│ Obra                 │ Detalle │ Bitácora │ Presupuesto          │
│  🏗️ Obra activa      │ Nombre de la obra (obligatorio) [      ] │
│  📋 Obras            │ …todos los datos…                        │
│  ➕ Nueva obra        │ [Guardar cambios] [Descartar cambios]    │
│ Configuración        │                                          │
│  🏷️ Rubros           │                               [💬 Agente]│
│  🏢 Proveedores      │                                          │
│ 👤 caro@… · Cerrar   │                                          │
└──────────────────────┴──────────────────────────────────────────┘
```

En el celular el menú arranca cerrado y se abre con «»»; el encabezado con la
obra activa queda fijo arriba.

## Agente

Sin herramientas nuevas. Trabaja sobre la obra activa en cualquier pantalla.

## Criterios de aceptación

- **UX-03-CA-1** — *Dado* que entro *entonces* el menú tiene el selector de obra activa y las pantallas Obra activa, Obras, Nueva obra, Rubros y Proveedores.
- **UX-03-CA-2** — *Dado* una obra activa *cuando* recorro todas las pantallas *entonces* arriba se ve su nombre, estado y avance.
- **UX-03-CA-3** — *Dado* una obra activa *entonces* se ve en Detalle, Bitácora y Presupuesto, y «Plata» no aparece en ninguna pantalla.
- **UX-03-CA-4** — *Cuando* edito todos los datos en Detalle y guardo *entonces* se guardan solo en esa obra. **CA-4b:** sin cambios, avisa y no escribe. **CA-4c:** si otro cambió un dato mientras edito otro, no lo piso.
- **UX-03-CA-5** — *Cuando* guardo con el nombre vacío *entonces* dice por qué, no guarda y conserva lo escrito.
- **UX-03-CA-6** — *Cuando* toco «Descartar cambios» *entonces* el formulario vuelve a lo guardado.
- **UX-03-CA-7** — *Cuando* toco «Abrir» en una obra del listado *entonces* queda activa y se abre su detalle.
- **UX-03-CA-8** — *Cuando* vuelvo a entrar (otra sesión u otro dispositivo) *entonces* la obra activa es la última que elegí. **CA-8b:** se guarda solo cuando cambia. **CA-8c:** si la obra recordada no existe o el dato es inválido, entra a la En curso más nueva. **CA-8d:** si no se puede guardar, la app sigue.
- **UX-03-CA-9** — *Cuando* creo una obra *entonces* queda activa y se abre su detalle.
- **UX-03-CA-10** — *Dado* que no hay obras *entonces* la app abre en «Nueva obra» con bienvenida, también si toco «Obra activa».
- **UX-03-CA-11** — *En* cualquier pantalla, el agente trabaja sobre la obra activa.
- **UX-03-CA-12** — *Cuando* cambio el municipio *entonces* el agente usa la normativa nueva.
- **UX-03-CA-13** — *Cuando* cambio el presupuesto de la obra *entonces* «Imprevistos» no cambia.
- **UX-03-CA-14** — Un nombre de obra con Markdown se muestra como texto en el encabezado y el listado.
- **UX-03-CA-15** — En Rubros agrego, subo, desactivo y reactivo un rubro; «Otros» no se desactiva. **CA-15b:** un rubro repetido no se agrega y se conserva lo escrito.
- **UX-03-CA-16** — Proveedores dice «Próximamente».

## Decisiones

| # | Pregunta | Decisión (22/10/2026) |
|---|---|---|
| D1 | Nombre de la pestaña «Plata» | «Presupuesto» (como #34) |
| D2 | ¿Menú abierto al entrar? | Abierto en la computadora, cerrado en el celular |
| D3 | Rubros y Proveedores | Rubros con pantalla (agregar, ordenar, desactivar). Proveedores «Próximamente» hasta #37 |
| D4 | Qué se edita en Detalle | Todos los datos del alta; autor y fecha de creación no |
| D5 | ¿Cambiar el presupuesto recalcula «Imprevistos»? | No |
| D6 | ¿Cambiar el municipio cambia la normativa? | Sí |
| D7 | Archivar o eliminar obras | Fuera: #26 |
| D8 | Sin obras | «Nueva obra» con bienvenida |
| D9 | Obra activa al entrar | La última en la que trabajó el usuario, recordada entre sesiones y dispositivos |
