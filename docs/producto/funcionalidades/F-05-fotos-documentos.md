# F-05 · Fotos y documentos

**Estado:** Borrador
**Prioridad:** Alta
**Depende de:** F-02 (opcionalmente F-03 y F-04 para vincular)

## Objetivo

Tener las fotos de avance y los papeles de cada obra (planos, permisos,
contratos, comprobantes) ordenados y a mano desde el celular, en lugar de
perdidos en la galería o el chat.

## Historias

- Como **socio**, quiero sacar una foto en la obra y adjuntarla a la nota del
  día para que la bitácora muestre lo que pasó.
- Como **socio**, quiero subir el plano aprobado y el permiso municipal de una
  obra para encontrarlos rápido.
- Como **socio**, quiero adjuntar el comprobante a un gasto para tener respaldo.
- Como **socio**, quiero pedirle al agente «mostrame las fotos de la platea de
  Lote 12» o «¿tenemos el plano aprobado de Hudson?».

## Alcance

**Incluye**
- Subir fotos (cámara o galería) e archivos PDF o imagen a una obra.
- Tipo de documento: Foto · Plano · Permiso · Contrato · Comprobante · Otro.
- Vincular opcionalmente un archivo a una nota de bitácora, una etapa (F-04) o un
  gasto (F-03).
- Galería de fotos por obra, ordenada por fecha, y lista de documentos por tipo.
- Fotos en la bitácora: miniaturas debajo de cada nota.
- Archivar un archivo (deja de verse, no se borra).
- El agente puede listar archivos y decir si existe un documento.

**No incluye** (por ahora)
- Leer el contenido de planos o PDFs con IA (por ejemplo, sacar medidas).
- Anotar o dibujar sobre fotos.
- Compartir archivos con gente fuera del equipo.
- Versionado de planos (v1, v2…): se sube como archivo nuevo.

## Datos

**Supabase Storage**: bucket privado `archivos-obra`, con ruta
`{obra_id}/{uuid}-{nombre}`. Solo usuarios logueados leen y suben; se accede con
URLs firmadas de corta duración.

**`archivos`**

| Campo | Tipo | Reglas |
|---|---|---|
| obra_id | bigint | FK `obras`, cascade |
| tipo | text | Foto · Plano · Permiso · Contrato · Comprobante · Otro |
| nombre | text | nombre original del archivo |
| ruta | text | ruta en Storage, única |
| mime | text | `image/*` o `application/pdf` |
| tamano_bytes | bigint | ≤ límite (ver D1) |
| descripcion | text | opcional |
| fecha | date | default hoy (fecha de la foto si se puede leer) |
| bitacora_id, etapa_id, gasto_id | bigint | opcionales, FK a cada tabla |
| archivado | bool | default `false` |
| creado_por | uuid | default `auth.uid()` |

RLS en la tabla y en el bucket: el equipo lee, sube y actualiza (para
archivar). Sin DELETE.

## Reglas de negocio

- **R1.** Solo se aceptan imágenes y PDF hasta el tamaño máximo (D1); el resto
  se rechaza con un mensaje claro antes de subir.
- **R2.** Las fotos se reducen antes de guardarse (D2) para que la app sea rápida
  en el celular.
- **R3.** Si la subida a Storage falla, no queda una fila «huérfana» en
  `archivos`, y viceversa.
- **R4.** Los archivos archivados no aparecen en galerías ni listas, pero siguen
  en la base y en Storage.
- **R5.** Nunca se expone una URL pública permanente: siempre URLs firmadas.

## Pantallas

1. En **Bitácora**: al agregar una nota, botón **📷 Adjuntar foto**; las miniaturas
   se ven debajo de cada nota.
2. Pestaña nueva **📁 Archivos** en 📋 Obras: arriba la galería de fotos y abajo los
   documentos agrupados por tipo. Botón **+ Subir** con tipo y descripción.
3. En **💰 Plata** (F-03): ícono 📎 en el gasto para adjuntar el comprobante.

## Agente

Herramientas nuevas:
- `listar_archivos(obra?, tipo?, texto?)` — nombres, fechas y descripciones.
- En el chat, el agente muestra las fotos encontradas como miniaturas debajo de
  la respuesta. **No** sube archivos por chat en esta versión (ver D3).

Ejemplos: «mostrame las fotos de la semana en Lote 12», «¿tenemos el permiso
de obra de Hudson?».

## Criterios de aceptación

- **F-05-CA-1** — *Dado* una obra *cuando* subo una foto como tipo Foto *entonces*
  aparece en su galería con fecha y autor.
- **F-05-CA-2** — *Dado* una nota de bitácora nueva *cuando* le adjunto una foto
  *entonces* la miniatura se ve debajo de la nota.
- **F-05-CA-3** — *Dado* un archivo de tipo no permitido o más grande que el límite
  *cuando* intento subirlo *entonces* se rechaza antes de subirlo, con un mensaje
  claro.
- **F-05-CA-4** — *Dado* un PDF de tipo Plano *cuando* lo subo *entonces* aparece en
  Documentos › Planos y se puede abrir.
- **F-05-CA-5** — *Dado* un gasto *cuando* le adjunto un comprobante *entonces* el
  gasto muestra 📎 y el archivo figura como tipo Comprobante.
- **F-05-CA-6** — *Dado* un archivo *cuando* lo archivo *entonces* deja de verse y
  sigue existiendo en la base y en Storage.
- **F-05-CA-7** — *Dado* un usuario sin login *cuando* pide un archivo o una URL del
  bucket *entonces* no obtiene nada.
- **F-05-CA-8** — *Dado* fotos de Lote 12 de esta semana *cuando* pido al agente
  «mostrame las fotos de la semana» con esa obra activa *entonces* responde con
  esas fotos y no inventa otras.
- **F-05-CA-9** — *Dado* que falla la subida a Storage *cuando* subo un archivo
  *entonces* no queda una fila en `archivos` y veo un error.

## Decisiones pendientes

| # | Pregunta | Recomendación | Decisión |
|---|---|---|---|
| D1 | ¿Tamaño máximo por archivo? | 10 MB para PDF; las fotos se reducen antes (D2). | ⏳ |
| D2 | ¿Calidad de las fotos guardadas? | Lado largo de 1600 px y JPEG al 80%: alcanza para ver detalles y pesa poco. | ⏳ |
| D3 | ¿El agente debería poder recibir fotos por chat («te mando la foto de la platea, guardala»)? | Más adelante. Primero, la subida desde la pestaña Archivos y la bitácora. | ⏳ |
| D4 | ¿Cuánto espacio necesitás? El plan gratis de Supabase trae 1 GB de Storage. | Arrancar en el plan gratis y medir; con fotos reducidas entran varios miles. | ⏳ |
| D5 | ¿Los planos tienen que verse dentro de la app o alcanza con abrir el PDF? | Abrir el PDF en una pestaña nueva. | ⏳ |
