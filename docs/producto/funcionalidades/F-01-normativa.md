# F-01 · Consultas de normativa

**Estado:** Hecha
**Prioridad:** Alta

## Objetivo

Responder preguntas sobre códigos de edificación municipales citando la
fuente, para no tener que buscar a mano en PDFs de cientos de páginas.

## Alcance actual

- Códigos cargados: **La Plata** y **Berazategui** (`docs/*.pdf`).
- Recuperación por similitud (Chroma) y respuesta del modelo con el contexto.
- Login con Supabase e historial privado por usuario (tabla `mensajes`).
- Con una **obra elegida**, la búsqueda se limita al código de su municipio (ver F-02).

## Criterios de aceptación (cubiertos por tests)

- **F-01-CA-1** — *Dado* un usuario logueado *cuando* pregunta por normativa
  *entonces* recibe una respuesta y puede ver los fragmentos usados. (E2E-12)
- **F-01-CA-2** — *Dado* una obra activa de La Plata *cuando* pregunta por
  normativa *entonces* solo se busca en el código de La Plata. (E2E-11)
- **F-01-CA-3** — *Dado* un usuario *cuando* chatea *entonces* su historial se
  guarda y nadie más del equipo lo puede leer. (E2E-16, LIVE-10, LIVE-11)

## Mejoras conocidas (sin priorizar)

- Sumar el código de **Quilmes** (hay una obra prevista ahí).
- Citar página y fuente dentro de la respuesta, no solo en «Contexto recuperado».
- El historial previo se le pasa al modelo como si todo fuera del usuario;
  conviene distinguir preguntas y respuestas.
