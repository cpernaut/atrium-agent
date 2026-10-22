# Casos de prueba end to end

Dos niveles, con el mismo criterio: cada caso es un recorrido de usuario con
resultado esperado verificable.

| Nivel | Dónde | Cuándo corre | Servicios |
|---|---|---|---|
| **E2E simulado** | `tests/e2e/` | En cada PR (workflow «Revisión de Claude») y con `pytest` | Supabase, OpenAI y Chroma simulados; la app de Streamlit es la real |
| **E2E real** | `tests/live/` | A mano: Actions → «E2E contra Supabase» → Run workflow | Supabase real; usuarios y obras temporales que se borran al final |

## E2E simulado — la app completa

| ID | Área | Caso | Resultado esperado |
|---|---|---|---|
| E2E-01 | Acceso | Login con contraseña incorrecta | Mensaje de error; no entra al chat |
| E2E-02 | Acceso | Login válido | Ve el agente, su email en la barra lateral y el chat |
| E2E-03 | Acceso | Cerrar sesión | Vuelve al login y la sesión queda limpia |
| E2E-04 | Obras | Crear obra completa | Mensaje de éxito; datos guardados; aparece en listado y métricas |
| E2E-05 | Obras | Crear obra sin nombre | Error «La obra necesita un nombre»; no se guarda |
| E2E-06 | Obras | Cambiar estado y avance | Se guarda solo en la obra elegida |
| E2E-07 | Obras | Filtrar por estado | El listado muestra solo ese estado |
| E2E-08 | Bitácora | Agregar nota con fecha | Se guarda con autor = usuario logueado y se muestra |
| E2E-09 | Bitácora | Nota vacía | Error «La nota está vacía»; no se guarda |
| E2E-10 | Obras | Tablas inexistentes en la base | Mensaje que indica correr `supabase_schema.sql`; la app no se rompe |
| E2E-11 | Agente | Pregunta con obra activa | Busca solo en el código del municipio; la ficha de la obra va al modelo |
| E2E-12 | Agente | Pregunta sin obra activa | Búsqueda sin filtro; el modelo sabe que no hay obra activa |
| E2E-13 | Agente | «¿Qué obras tengo en curso?» | Responde con datos reales del tracker, filtrados por estado |
| E2E-14 | Agente | «Anotá… avance 40%» con obra activa | Nota y avance guardados; avisos visibles; se ven luego en Obras |
| E2E-15 | Agente | Pedido con obra ambigua | No escribe nada; pide aclarar |
| E2E-16 | Historial | Una pregunta en el chat | Pregunta y respuesta guardadas para el usuario |

## E2E real — reglas de la base (Supabase)

| ID | Área | Caso | Resultado esperado |
|---|---|---|---|
| LIVE-01 | Seguridad | Sin login, leer obras, bitácora e historial | No devuelve nada |
| LIVE-02 | Seguridad | Sin login, crear una obra | Rechazado |
| LIVE-03 | Seguridad | Registrarse sin invitación | Rechazado («Allow new users to sign up» desactivado) |
| LIVE-04 | Obras | Crear obra | Queda firmada por su autor; defaults Planificación / ARS / 0% |
| LIVE-05 | Equipo | B ve y edita la obra de A | Permitido; A ve el cambio |
| LIVE-06 | Integridad | Avance 150, −1 o moneda EUR salteando la app | La base lo rechaza |
| LIVE-07 | Integridad | Borrar una obra | No se borra nada |
| LIVE-08 | Bitácora | B anota en la obra de A | Guardada con autor y fecha de hoy; A la ve |
| LIVE-09 | Integridad | Nota sin texto salteando la app | La base la rechaza |
| LIVE-10 | Privacidad | B lee el historial de A | No ve nada; A ve el suyo |
| LIVE-11 | Privacidad | B guarda mensajes a nombre de A | Rechazado |
| LIVE-12 | Agente | Herramientas del agente sobre la base real | Leen, anotan y actualizan; rechazan avance 150 |

## Cómo correr

```bash
pytest                      # unitarios + E2E simulado (los LIVE se saltean)
pytest tests/e2e -v         # solo E2E simulado
```

Para el nivel real, cargar en el repo los secrets `E2E_SUPABASE_URL`,
`E2E_SUPABASE_ANON_KEY` y `E2E_SUPABASE_SERVICE_ROLE_KEY` (Supabase → Project
Settings → API Keys) y correr el workflow «E2E contra Supabase» desde Actions.
