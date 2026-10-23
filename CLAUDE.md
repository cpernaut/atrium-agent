# CLAUDE.md — Atrium Studio (repo `atrium-agent`)

Instrucciones para Claude al trabajar en este repo. Qué construimos y por qué:
[`docs/producto/`](docs/producto/README.md). Leé la ficha de la funcionalidad
antes de tocar código.

## Contexto en una línea

App Streamlit para Carolina y sus socios en Atrium: agente de normativa de obra
(LangGraph + Chroma + OpenAI) más un tracker de obras, todo con login y datos en
Supabase. Desplegada en Streamlit Community Cloud desde `main`.

## Flujo de trabajo

- **Nunca** pushear a `main`: rama + PR. Mergear `main` redespliega la app real.
- Implementar solo fichas en estado `Lista`. Si falta una decisión, preguntarla
  en vez de inventarla. Si un pedido contradice una ficha, avisarlo primero.
- Un PR por ficha. En el mismo PR: código, tests, ficha en `Hecha`, roadmap,
  glosario si hay términos nuevos, y `docs/casos-e2e.md`.
- **Auto-merge:** al abrir un PR, activarle el auto-merge
  (`PUT repos/{owner}/{repo}/pulls/{n}/ccr/auto_merge`). Se mergea solo cuando
  pasan los checks obligatorios de `main`: «Tests y lint», «Esquema y seguridad
  en Postgres», «Revisión sin bloqueantes» y «Esquema aplicado». Si la revisión
  marca bloqueantes, arreglarlos en el mismo PR.
- Si el PR cambia `supabase_schema.sql`, la descripción del PR dice
  **«Antes de mergear: correr supabase_schema.sql»**, porque el esquema no se
  aplica solo, y el check «Esquema aplicado» frena el merge hasta que el PR tenga
  la etiqueta `esquema aplicado`. Con el conector de Supabase se puede aplicar y
  verificar, pidiéndolo antes; después se pone la etiqueta. Si el check quedara trabado
  con el esquema ya aplicado (eventos de GitHub fuera de orden), se destraba
  sacando y volviendo a poner la etiqueta.
- Commits y PRs en español.

## Arquitectura (respetarla)

```
app.py            orquestación y render; nada de lógica de negocio
navegacion.py     menú de la izquierda (st.Page + page_link) e ir_a(); #49
*_ui.py           pantallas de Streamlit (obras_ui.py, plata_ui.py, rubros_ui.py…)
ui_utils.py       helpers de pantalla (texto_seguro)
atrium/           dominio. NUNCA importa streamlit
  obras.py        acceso a datos de un área: funciones que reciben el `client`
  finanzas.py     F-03: rubros, gastos, presupuesto, conversión y resumen
  proveedores.py  F-06: lista de proveedores, calificaciones y compras
  cotizaciones.py dólar MEP desde una fuente pública (único acceso a internet)
  obra_tools.py   herramientas del agente: cierran sobre el client del usuario
                  (las de proveedores, en proveedor_tools.py)
  rag.py          grafo LangGraph: classify -> retrieve -> agente_obra (+ tools)
supabase_schema.sql  todo el esquema, idempotente
```

- Un módulo de dominio por área nueva (`atrium/finanzas.py`, `atrium/cronograma.py`,
  `atrium/archivos.py`), con el mismo patrón que `atrium/obras.py`: funciones
  puras sobre el `client`, errores envueltos en una excepción propia (`XxxError`)
  con mensajes en español listos para mostrar.
- Las herramientas nuevas del agente van en `atrium/obra_tools.py` (o un
  `*_tools.py` hermano) y se registran en `build_obra_tools`. Nunca lanzan
  excepciones: devuelven el error como texto. Las que escriben agregan una línea
  a `acciones` y su docstring dice «Usala SOLO si el usuario pide…».
- Datos cargados por usuarios que vuelven al modelo (notas, comentarios,
  nombres): toda herramienta se registra con `turno.herramienta(fn)`, que marca
  todo lo que devuelve como dato, y las de escritura empiezan con
  `turno.bloqueo(..., ACCION)` (`atrium/guardia.py`): solo
  escriben si el mensaje del usuario lo pide, así una pregunta o una instrucción
  escondida en los datos nunca hacen escribir al agente.
- Las pantallas reciben el `supabase` de la sesión (cliente con el login del
  usuario): así aplica RLS. **No** usar la clave service_role en la app.

## Base de datos

- Todo el esquema está en `supabase_schema.sql` y debe poder correrse varias
  veces: `create table if not exists`, `drop policy if exists` + `create policy`,
  `alter table … add column if not exists`.
- Toda tabla nueva: `enable row level security`, políticas para `authenticated`,
  columna `creado_por uuid default auth.uid()` y **sin política de DELETE**
  (se anula o archiva con un booleano).
- Las restricciones van también en la base (`check`, `not null`), no solo en Python.
- Montos: `numeric(14,2)` + columna `moneda` (`ARS`/`USD`). Nunca sumar monedas
  distintas sin tipo de cambio explícito. Cálculos con `Decimal`, nunca `float`.
- Qué columnas se pueden editar se fija en la base con permisos por columna
  (`revoke update` + `grant update (…)`), además de la lista en el dominio
  (p. ej. `CAMPOS_EDITABLES_ITEM`, `CAMPOS_EDITABLES_GASTO`). Nunca se edita la
  obra, el autor ni la fecha de carga de un registro; la fecha de un gasto (la
  del pago) sí se edita (#25).
- «Borrar» en la interfaz es siempre anular: confirmación en `st.dialog`
  controlado por `session_state` (así se puede testear) con `on_dismiss`.
- Cada tabla nueva suma sus chequeos de RLS e integridad en `tests/sql/`
  (corren en Postgres real en cada PR).

## Nombres e idioma

- Interfaz, mensajes de error y respuestas del agente: **español rioplatense con
  voseo** («cargá», «elegí»).
- Código y docstrings en inglés; los **nombres del dominio en español**, tal cual
  figuran en [`docs/producto/glosario.md`](docs/producto/glosario.md) (tablas,
  columnas, valores, herramientas del agente).
- Widgets de Streamlit con `key=` estable cuando un test los usa.

## Accesibilidad (pantallas)

- Todo campo con etiqueta visible; los obligatorios dicen «(obligatorio)».
- El estado nunca depende solo del color: siempre también en palabras.
- Montos con formato argentino y su moneda (`finanzas.formato_monto`).
- Ante un error, el formulario conserva lo escrito; tras guardar, se limpia.
- Acciones irreversibles o de anulación piden confirmación explícita.

## Tests (obligatorios)

```bash
pytest            # unitarios + E2E simulado; los live se saltean sin credenciales
ruff check . && ruff format --check .
```

- **Unitarios** del dominio con `tests/fake_supabase.py`. Si la tabla nueva tiene
  defaults, agregarlos en `_DEFAULTS` del fake para que imite a la base real.
- **E2E simulado** (`tests/e2e/`): al menos un test por criterio de aceptación,
  con el ID de la ficha en el docstring (`"""F-03-CA-2: …"""`). La primera oración
  del docstring es lo que el reporte de cada corrida muestra como «Qué prueba»:
  que se entienda sin leer el código. Usa la app real
  vía `AppTest` y los dobles de `tests/fakes.py`.
- **E2E real** (`tests/live/`): todo lo que dependa de RLS, constraints o Storage
  de Supabase. Datos con prefijo `[E2E]` y limpieza garantizada.
- Ningún test llama a OpenAI ni a internet. El modelo se simula con
  `ToolCallingFake` y el buscador con `RecordingStore`.
- Los tests no deben modificar `chroma_db/`. Si aparece modificado en
  `git status`, restaurarlo antes de commitear.

## Seguridad

- Secretos solo en Secrets de Streamlit o de GitHub; nunca en el código, el chat
  ni los logs. `.env` y `.streamlit/secrets.toml` están en `.gitignore`.
- Antes de exponer datos nuevos, preguntarse: ¿los ve alguien sin login? La
  respuesta tiene que ser no, y tiene que haber un test `live` que lo pruebe.
- Texto cargado por usuarios dentro de `st.markdown`, `st.caption`, avisos y
  errores: siempre con `texto_seguro()` (evita links e imágenes externas
  inyectadas). Respuestas del agente: con `respuesta_segura()` (mantiene el
  formato pero nunca carga imágenes).
- Llamadas a internet solo a URLs fijas en `Settings`, con timeout, y
  validando la respuesta como dato no confiable.

## Entorno

- Python 3.14, igual que producción en Streamlit Cloud (Manage app → Settings).
  CI corre con la misma versión. `requirements.txt` con versiones
  fijas; agregar dependencias pinneadas y probar que instalen en Linux.
- Secrets que la app espera: `OPENAI_API_KEY`, `SUPABASE_URL`,
  `SUPABASE_ANON_KEY`, y opcionalmente `LANGSMITH_*`.
