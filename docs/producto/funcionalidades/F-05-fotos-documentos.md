# F-05 · Fotos y documentos

**Estado:** Borrador (D1, D2, D5 a D8 decididas el 30/10/2026; faltan D3, D4 y D9 a D12)
**Prioridad:** Alta
**Depende de:** F-02 (obras y bitácora), F-03 (gastos e ítems del presupuesto) · Issue: #22

## Objetivo

Tener las fotos de avance y los papeles de cada obra (planos, permisos,
contratos, comprobantes, cotizaciones) ordenados y a mano desde el celular, en
lugar de perdidos en la galería o el chat.

## Historias

- Como **socia**, quiero sacar una foto en la obra con la cámara del celular y
  adjuntarla a la nota del día, para que la bitácora muestre lo que pasó.
- Como **socia**, quiero subir el plano (PDF o DWG), el permiso municipal o un
  contrato a la obra, para encontrarlos rápido.
- Como **socia**, quiero adjuntar el comprobante a un gasto para tener respaldo.
- Como **socia**, quiero adjuntar la cotización de un proveedor a un ítem del
  presupuesto.
- Como **socia**, quiero preguntarle al agente «¿tenemos el plano aprobado de
  Hudson?» o «¿qué fotos hay de la platea de Lote 12?».

## Alcance

**Incluye**
- Subir uno o varios archivos: fotos (cámara o galería del celular), PDF,
  imágenes, Word, Excel y AutoCAD (DWG, DXF). El botón «Subir» del celular ya
  ofrece «Tomar foto», «Galería» o «Archivos».
- Cada archivo pertenece a una obra y, opcionalmente, a **una** nota de
  bitácora, **un** gasto o **un** ítem del presupuesto (D8, D9).
- Tipo de archivo: Foto · Plano · Permiso · Contrato · Comprobante · Cotización · Otro.
- Pestaña **📁 Archivos** de la obra activa: galería de fotos por fecha y
  documentos agrupados por tipo.
- 📎 en la bitácora, en cada gasto y en cada ítem del presupuesto: adjuntar y ver
  sus archivos (miniaturas en el caso de las fotos).
- Ver: fotos dentro de la app; PDF en una pestaña nueva; Word, Excel y AutoCAD se
  descargan y se abren con las apps del celular o la compu (D5, D7).
- Archivar un archivo (deja de verse, no se borra).
- El agente lista archivos y dice si existe un documento (solo lectura).

**No incluye** (por ahora)
- Ver planos de AutoCAD dentro de la app (visor de Autodesk): idea #57.
- Leer el contenido de planos o PDFs con IA (sacar medidas, resumir un contrato).
- Anotar o dibujar sobre fotos; compartir archivos con gente fuera del equipo.
- Versionado de planos (v1, v2…): se sube como archivo nuevo.
- Vincular a etapas: cuando exista F-04.

## Datos

**Supabase Storage** (D6): bucket **privado** `archivos-obra`, con límite de
50 MB por archivo y lista de tipos permitidos configurados en el propio bucket.
Ruta `{obra_id}/{uuid}.{extensión}`: el nombre que puso el usuario nunca forma
parte de la ruta. Políticas en `storage.objects`: solo `authenticated` lee y
sube en ese bucket; sin DELETE. Se accede con URLs firmadas de pocos minutos.

**`archivos`**

| Campo | Tipo | Reglas |
|---|---|---|
| obra_id | bigint | FK `obras`, cascade; obligatorio |
| tipo | text | Foto · Plano · Permiso · Contrato · Comprobante · Cotización · Otro |
| nombre | text | nombre original, limpio (SEG-01), 1 a 200 caracteres |
| ruta | text | ruta en Storage, única |
| mime | text | de la lista permitida (R1) |
| extension | text | de la lista permitida (R1) |
| tamano_bytes | bigint | 1 a 52 428 800 (50 MB, D1) |
| descripcion | text | opcional, limpia (SEG-01), hasta 500 |
| fecha | date | default hoy; en fotos, la fecha en que se sacó si se puede leer |
| bitacora_id | bigint | FK `bitacora`, opcional |
| gasto_id | bigint | FK `gastos`, opcional |
| presupuesto_item_id | bigint | FK `presupuesto_items`, opcional |
| archivado | bool | default `false` |
| creado_por | uuid | default `auth.uid()` |
| created_at | timestamptz | default `now()` |

- Como mucho uno de `bitacora_id`, `gasto_id` y `presupuesto_item_id` (D9);
  ninguno = archivo de la obra en general. Un trigger verifica que el vínculo sea
  de la **misma obra**.
- RLS en la tabla: el equipo lee, sube y actualiza solo `tipo`, `descripcion` y
  `archivado` (permisos por columna). Sin DELETE.

## Reglas de negocio

- **R1. Formatos permitidos:** JPG, PNG, WEBP, HEIC (fotos), PDF, DOC, DOCX, XLS,
  XLSX, CSV, DWG y DXF. Se valida la extensión **y** el contenido real del
  archivo (sus primeros bytes), antes de subir. No se aceptan SVG, HTML,
  ejecutables ni Office con macros (DOCM, XLSM).
- **R2. Tamaño:** hasta 50 MB por archivo (D1); se rechaza antes de subir, con
  un mensaje claro.
- **R3. Fotos:** se reducen a 1600 px del lado largo, JPEG al 80 % (D2), y se les
  quita la ubicación GPS y el resto de los metadatos (D10). Las HEIC del iPhone se
  convierten a JPEG (D12).
- **R4. Subida atómica:** si falla la subida a Storage no queda una fila en
  `archivos`; si falla la fila, se intenta borrar el objeto subido y se avisa.
- **R5. Archivar:** deja de verse en galerías y listas; sigue en la base y en
  Storage, y se puede restaurar desde «Mostrar archivados».
- **R6. Privacidad:** nunca hay URLs públicas; siempre firmadas y de corta
  duración. Los archivos de Word, Excel y AutoCAD se descargan (no se abren dentro
  de la app).
- **R7.** Nombre y descripción pasan por la revisión de SEG-01 y se muestran con
  `texto_seguro`.

## Pantallas

```
📁 Archivos (pestaña de la obra activa)
[+ Subir archivos]   Tipo [Todos ▾]   ☐ Mostrar archivados
Fotos
 ▢ ▢ ▢ ▢   (miniaturas por fecha; tocar = ver grande)
Documentos
 Planos      · Plano planta baja.pdf (2,1 MB) · 12/10/2026 · caro   [Abrir] [⋯]
             · Planta baja.dwg (8,4 MB)                              [Descargar]
 Comprobantes· Factura hierro.pdf  → gasto «Seña hierro»             [Abrir]

Subir archivos
 Archivos (obligatorio) [Tomar foto / Galería / Archivos]   (varios a la vez, D11)
 Tipo (obligatorio) [Foto ▾]   Descripción [ ]
 Vincular a: (•) La obra  ( ) Nota de bitácora [▾]  ( ) Gasto [▾]  ( ) Ítem [▾]
```

- En la **Bitácora**, el formulario de nota tiene «📎 Adjuntar»; las miniaturas
  se ven debajo de cada nota.
- En el **Presupuesto**, cada gasto y cada ítem tienen 📎 con la cantidad de
  archivos; al tocarlo se ven y se pueden adjuntar más.
- Estado siempre en palabras («Subiendo…», «✅ 3 archivos subidos», «⚠️ No se
  subió X: es más grande que 50 MB»).

## Agente

- `listar_archivos(obra?, tipo?, texto?)`: nombre, tipo, fecha, autor, a qué está
  vinculado y descripción. Todo lo que devuelve va marcado como dato (SEG-01).
- No sube ni archiva archivos por chat (D3).

Ejemplos: «¿tenemos el permiso de obra de Hudson?», «¿qué comprobantes hay del
gasto de hierro?».

## Criterios de aceptación

- **F-05-CA-1** — *Dado* una obra *cuando* subo una foto como tipo Foto *entonces*
  aparece en su galería con fecha y autor, reducida y sin ubicación GPS.
- **F-05-CA-2** — *Dado* una nota de bitácora *cuando* le adjunto una foto
  *entonces* la miniatura se ve debajo de la nota.
- **F-05-CA-3** — *Dado* un gasto *cuando* le adjunto un PDF como Comprobante
  *entonces* el gasto muestra 📎 1 y el archivo figura en Documentos › Comprobantes.
- **F-05-CA-4** — *Dado* un ítem del presupuesto *cuando* le adjunto una cotización
  en Excel *entonces* el ítem muestra 📎 1 y el archivo se puede descargar.
- **F-05-CA-5** — *Dado* un plano en PDF y otro en DWG *cuando* los subo a la obra
  *entonces* el PDF se abre en una pestaña nueva y el DWG se descarga.
- **F-05-CA-6** — *Dado* un archivo de más de 50 MB, un SVG, un DOCM o un archivo
  cuyo contenido no coincide con su extensión *cuando* intento subirlo *entonces*
  se rechaza antes de subir, con el motivo.
- **F-05-CA-7** — *Dado* varios archivos elegidos a la vez *cuando* subo *entonces*
  se suben todos y se informa cuáles no y por qué.
- **F-05-CA-8** — *Dado* un archivo *cuando* lo archivo (con confirmación)
  *entonces* deja de verse, sigue en la base y en Storage, y se puede restaurar.
- **F-05-CA-9** — *Dado* que falla la subida a Storage *cuando* subo *entonces* no
  queda una fila en `archivos` y veo un error.
- **F-05-CA-10** — *Dado* un nombre de archivo con Markdown o una orden para el
  agente *cuando* lo subo *entonces* se limpia o se rechaza (SEG-01) y nunca se
  interpreta al mostrarlo.
- **F-05-CA-11** — *Dado* «¿tenemos el plano aprobado?» por chat *cuando* existe un
  Plano en la obra activa *entonces* el agente lo nombra, y no inventa otros.
- **LIVE** — sin login no se lista ni se descarga nada del bucket ni de la tabla;
  la base rechaza un vínculo a un gasto de otra obra, más de un vínculo, un tipo o
  una extensión fuera de la lista y un tamaño mayor a 50 MB.

## Decisiones

| # | Pregunta | Recomendación | Decisión |
|---|---|---|---|
| D1 | ¿Tamaño máximo por archivo? | 50 MB | ✅ 50 MB (30/10/2026) |
| D2 | ¿Calidad de las fotos guardadas? | 1600 px del lado largo, JPEG al 80 % | ✅ Así (30/10/2026) |
| D3 | ¿El agente recibe fotos por chat («guardá esta foto de la platea»)? | Más adelante; primero las pantallas | ⏳ |
| D4 | ¿Espacio? (Supabase gratis trae 1 GB) | Arrancar en el plan gratis y mostrar el espacio usado en 📁 Archivos; pasar a Pro (USD 25/mes) si hace falta | ⏳ |
| D5 | ¿Cómo se ven los archivos? | Fotos en la app, PDF en pestaña nueva, el resto se descarga | ✅ Así (30/10/2026) |
| D6 | ¿Dónde se guardan? | Supabase Storage | ✅ Supabase Storage (30/10/2026) |
| D7 | ¿Visor de AutoCAD? | Descargar ahora; visor de Autodesk más adelante | ✅ Descargar; visor como idea #57 (30/10/2026) |
| D8 | ¿A qué se vinculan? | Obra, nota de bitácora, gasto e ítem del presupuesto | ✅ Esos cuatro (30/10/2026) |
| D9 | ¿Un archivo puede estar vinculado a varias cosas a la vez? | No: a la obra y como mucho a una nota, un gasto o un ítem | ⏳ |
| D10 | ¿Quitarle a las fotos la ubicación GPS y demás metadatos? | Sí (privacidad de las obras y los clientes) | ⏳ |
| D11 | ¿Subir varios archivos a la vez? | Sí, con el mismo tipo y vínculo | ⏳ |
| D12 | ¿Fotos HEIC del iPhone? | Convertirlas a JPEG al subir | ⏳ |
