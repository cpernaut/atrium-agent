# Casos de prueba end to end

Dos niveles, con el mismo criterio: cada caso es un recorrido de usuario con
resultado esperado verificable.

| Nivel | Dónde | Cuándo corre | Servicios |
|---|---|---|---|
| **E2E simulado** | `tests/e2e/` | En cada PR (workflow «Revisión del PR») y con `pytest` | Supabase, OpenAI y Chroma simulados; la app de Streamlit es la real |
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

## E2E simulado — F-03 Presupuesto y gastos (`tests/e2e/test_plata_flows.py`)

| ID | Caso | Resultado esperado |
|---|---|---|
| F-03-CA-1 | Cargar presupuesto en tres rubros | Resumen por rubro, en orden de obra, y total |
| F-03-CA-2 | Registrar un gasto | Aparece en «Últimos gastos» y suma en su rubro y en el total |
| F-03-CA-3 | Gasto de hoy con MEP 1190/1210 | Se guarda cotización 1200, automática |
| F-03-CA-4 | Gasto de un sábado | Toma la cotización del viernes anterior |
| F-03-CA-5 | Fuente de cotizaciones caída | Se guarda sin cotización, con aviso y opción de cargarla a mano |
| F-03-CA-6 | Corregir la cotización a 1180 | Queda «corregida a mano» y el resumen la usa |
| F-03-CA-6b | Ítem de presupuesto sin cotización, corregido a mano | Queda manual y el total deja de estar incompleto |
| F-03-CA-7 | USD 1.000 + ARS 600.000 a 1200 | ARS 1.800.000 o USD 1.500 |
| F-03-CA-8 | Gasto en USD sin cotización, vista en ARS | No suma y avisa «Total incompleto» |
| F-03-CA-9 | Anular un gasto | Pide confirmación; deja de sumar, tachado y «Anulado», sigue en la base |
| F-03-CA-10 | Monto 0 o sin descripción | Mensaje claro, nada guardado, el formulario conserva lo escrito |
| F-03-CA-11 | «Cargá 350 mil pesos de hierro» por chat | Gasto en Estructura con cotización del día; aviso; se ve en 💰 Plata |
| F-03-CA-11b | Rubro inexistente por chat | No guarda nada; el agente pide aclarar |
| F-03-CA-12 | «¿En qué rubro nos pasamos?» | Responde con desvíos reales por rubro |
| F-03-SEG-1 | Descripción con Markdown de imagen o link | Se muestra como texto, no se interpreta |
| F-03-A11Y-1 | Campos de la pestaña | Todos con etiqueta visible; los obligatorios lo dicen |
| F-03-A11Y-2 | Rubro excedido | El estado se lee en palabras, no solo por color |

## Esquema y seguridad en Postgres (`tests/sql/`, en cada PR)

Aplica `supabase_schema.sql` dos veces en un Postgres 16 limpio y verifica:
precarga de rubros; defaults; que la base rechace montos ≤ 0, descripciones
vacías o largas, monedas, fechas futuras, cotizaciones inválidas o sin origen y
rubros inexistentes; rubros únicos; que nada se pueda borrar; que el equipo
comparta los datos; y que sin login no se vea ni escriba nada.

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
| LIVE-13 | Seguridad | Sin login, leer rubros, gastos o presupuesto, o crear un gasto | No ve nada; rechazado |
| LIVE-14 | Rubros | Precarga | Están los 18 rubros, incluido Steel frame |
| LIVE-15 | Integridad | Gastos inválidos salteando la app | La base los rechaza |
| LIVE-16 | Gastos | B ve, corrige y anula el gasto de A; borrar | Permitido salvo borrar |
| LIVE-17 | Rubros | Alta de rubro y duplicado con otras mayúsculas | Se crea; el duplicado se rechaza; no se borra |

## Cómo correr

```bash
pytest                      # unitarios + E2E simulado (los LIVE se saltean)
pytest tests/e2e -v         # solo E2E simulado
```

Para el nivel real, cargar en el repo los secrets `E2E_SUPABASE_URL`,
`E2E_SUPABASE_ANON_KEY` y `E2E_SUPABASE_SERVICE_ROLE_KEY` (Supabase → Project
Settings → API Keys) y correr el workflow «E2E contra Supabase» desde Actions.
