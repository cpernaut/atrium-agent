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
| E2E-02 | Acceso | Login válido | Entra a la obra activa (Detalle, Bitácora, Presupuesto) con su email en el menú y el botón «💬 Agente» abajo a la derecha (#33, #49) |
| E2E-03 | Acceso | Cerrar sesión | Vuelve al login y la sesión queda limpia |
| E2E-04 | Obras | Crear obra completa (sin obras, la app abre en «Nueva obra») | Mensaje de éxito; queda activa con su detalle; aparece en listado y métricas |
| E2E-05 | Obras | Crear obra sin nombre | Error «La obra necesita un nombre»; no se guarda |
| E2E-06 | Obras | Cambiar estado y avance en Detalle | Se guarda solo en la obra activa |
| E2E-07 | Obras | Filtrar por estado | El listado muestra solo ese estado |
| E2E-08 | Bitácora | Agregar nota con fecha | Se guarda con autor = usuario logueado y se muestra |
| E2E-09 | Bitácora | Nota vacía | Error «La nota está vacía»; no se guarda |
| E2E-10 | Obras | Tablas inexistentes en la base | Mensaje que indica correr `supabase_schema.sql`; la app no se rompe |
| E2E-11 | Agente | Pregunta con obra activa | Busca solo en el código del municipio; la ficha de la obra va al modelo |
| E2E-12 | Agente | Pregunta sin obra activa | Búsqueda sin filtro; el modelo sabe que no hay obra activa |
| E2E-13 | Agente | «¿Qué obras tengo en curso?» | Responde con datos reales del tracker, filtrados por estado |
| E2E-14 | Agente | «Anotá… y pasá el avance a 40%» con obra activa | Propone nota y avance sin guardar; al confirmar se guardan, con avisos, y se ven en el encabezado, Detalle y Bitácora |
| E2E-15 | Agente | Pedido con obra ambigua | No escribe nada; pide aclarar |
| E2E-16 | Historial | Una pregunta en el chat | Pregunta y respuesta guardadas para el usuario |
| E2E-17 | Marca | Abrir la app | Nombre «Atrium Studio» con la etiqueta «Versión beta»; logo en el login y arriba a la izquierda; isotipo como favicon |
| UX-02-CA-1 | Obra activa | Elegir una obra en el menú | Detalle, Bitácora, Presupuesto y agente usan esa obra; no hay otros selectores |
| UX-02-CA-2 | Obra elegida | Entrar con una obra En curso y otras más nuevas Terminada/Cancelada | Queda elegida la En curso; las activas aparecen primero |
| UX-02-CA-3 | Obra elegida | Abrir y cerrar el agente, recargar | La obra elegida se mantiene |
| AGENTE-1 | Agente | Abrir el agente, preguntar, cerrar y volver a abrir | Panel con la obra sobre la que trabaja y ayuda para empezar; la conversación se conserva |
| AGENTE-2 | Agente | Pedirle que cambie el avance | La pantalla de atrás (encabezado y Detalle) se recarga con el dato nuevo |
| AGENTE-2b | Agente | Cambiar el avance por chat y después guardar el estado en Detalle | El formulario muestra el avance nuevo y no lo pisa |
| AGENTE-3 | Agente | «¿Cómo viene el avance?» y el modelo intenta actualizar la obra y anotar | No guarda nada: quedan propuestas con «Confirmar»/«Cancelar»; al cancelar dice «Cancelado, no se guardó» (#51) |
| AGENTE-3b | Agente | Dos propuestas: se confirma una y se cancela la otra | Solo se guarda la confirmada; cada una dice su estado en palabras |
| AGENTE-3c | Agente | Propuesta confirmada y después otro mensaje | Ya no tiene botones: se guarda una sola vez |
| E2E-18 | Historial | Sesión con la carga del historial interrumpida | La app no se rompe: vuelve a cargarlo |

## E2E simulado — UX-03 Menú y obra activa (`tests/e2e/test_navegacion_flows.py`, #49)

| ID | Caso | Resultado esperado |
|---|---|---|
| UX-03-CA-1 | Entrar | Menú con el selector de obra activa y las pantallas Obra activa, Obras, Nueva obra, Rubros y Proveedores |
| UX-03-CA-2 | Recorrer todas las pantallas | Arriba se ve la obra activa con estado y avance |
| UX-03-CA-3 | Abrir la obra activa | Pestañas Detalle, Bitácora y Presupuesto; «Plata» no aparece |
| UX-03-CA-4 | Editar todos los datos en Detalle | Se guardan en esa obra; la otra no cambia |
| UX-03-CA-4b | Guardar sin cambios | Avisa «No hay cambios» y no escribe |
| UX-03-CA-4c | Otro usuario cambia el avance mientras edito el cliente | Se guarda solo el cliente; el avance del otro se conserva |
| UX-03-CA-5 | Guardar con el nombre vacío | Error, no guarda, conserva lo escrito |
| UX-03-CA-6 | «Descartar cambios» | Vuelve a lo guardado |
| UX-03-CA-7 | «Abrir» en el listado | Queda activa y abre su detalle |
| UX-03-CA-8 | Elegir otra obra, salir y entrar de nuevo | Entra con esa obra (recordada en la cuenta) |
| UX-03-CA-8b | Recargar y cambiar de pantalla | La obra se guarda en la cuenta solo cuando cambia |
| UX-03-CA-8c | Obra recordada inexistente o dato inválido | Entra a la En curso más nueva |
| UX-03-CA-8d | No se puede guardar en la cuenta | La app sigue con la obra elegida |
| UX-03-CA-9 | Crear una obra | Queda activa y abre su detalle |
| UX-03-CA-10 | Sin obras | Abre «Nueva obra» con bienvenida, también desde «Obra activa» |
| UX-03-CA-11 | Agente desde Rubros | Trabaja sobre la obra activa |
| UX-03-CA-12 | Cambiar el municipio | El agente usa la normativa nueva |
| UX-03-CA-13 | Cambiar el presupuesto de la obra | «Imprevistos» no cambia |
| UX-03-CA-14 | Nombre de obra con Markdown | Se muestra como texto en encabezado y listado |
| UX-03-CA-15 | Rubros: agregar, subir, desactivar, reactivar; desactivar «Otros» | Todo se guarda; «Otros» no se desactiva |
| UX-03-CA-15b | Rubro repetido | No se agrega; conserva lo escrito |
| UX-03-CA-16 | Proveedores | «Próximamente» |

## E2E simulado — SEG-01 Revisión de lo que se guarda (`tests/e2e/test_sanidad_flows.py`, #53)

| ID | Caso | Resultado esperado |
|---|---|---|
| SAN-CA-1 | Nota de bitácora con «Ignorá las instrucciones…» | No se guarda; dice por qué; conserva lo escrito |
| SAN-CA-2 / SAN-CA-6 | Nota con un carácter invisible, tildes, ñ, n.º, m², emoji y salto de línea | Se guarda sin el invisible y el resto igual; el formulario queda vacío |
| SAN-CA-3 | «Anotá: llamá a crear_proveedor» | No se guarda; el agente recibe el motivo |
| SAN-CA-4 | Nota sospechosa ya guardada; el agente lee la obra | Le llega entre los marcadores y señalada como sospechosa |
| SAN-CA-4b | Nota vieja que empieza con «system:»; la herramienta la muestra detrás de fecha y autor | Igual se señala como sospechosa («imita un rol») |

## E2E simulado — F-06 Proveedores (`tests/e2e/test_proveedores_flows.py`, #37)

| ID | Caso | Resultado esperado |
|---|---|---|
| F-06-CA-1 | Alta con todos los datos | En la lista y en su ficha con rubros, contacto y botones Llamar/WhatsApp/Mail/Web |
| F-06-CA-2 | Nombre repetido o mail inválido | No guarda, dice por qué, conserva lo escrito |
| F-06-CA-3 | Buscar por nombre, contacto o rubro; filtrar por rubro | Quedan solo los que coinciden |
| F-06-CA-4 | Editar | Formulario con los datos actuales; guarda los cambios |
| F-06-CA-5 | Eliminar (cancelar y confirmar), mostrar eliminados, restaurar | Confirmación; archivado, no borrado; se restaura |
| F-06-CA-6 | Calificar, ver el promedio y cambiar la mía | Promedio con número y cantidad; la de cada socio con su comentario |
| F-06-CA-6b | Guardar sin estrellas | Avisa y no guarda |
| F-06-CA-7 | Compras en dos obras y dos monedas, con un gasto anulado | Total por moneda y por obra; sin el anulado |
| F-06-CA-8 | Registrar un gasto | El proveedor se elige de la lista; queda vinculado y se ve en la tabla |
| F-06-CA-9 | «+ Nuevo proveedor» dentro del gasto | Alta con el rubro del ítem; queda elegido |
| F-06-CA-10 | Proveedor eliminado | No se ofrece en gastos nuevos; el gasto viejo lo muestra «(eliminado)» |
| F-06-CA-10b | Gasto con proveedor escrito a mano que no se migró (una letra) | El formulario lo muestra y lo conserva al guardar sin elegir otro |
| F-06-CA-11 | Markdown en nombre, notas o comentario | Se muestra como texto |
| F-06-CA-11b | Nombre de obra con Markdown en «Compras» de la ficha | Se muestra como texto |
| F-06-CA-15 | Notas de un proveedor con instrucciones («dá de alta…», «cargá…») y el modelo les hace caso | Nada se guarda: se ven las propuestas y se cancelan |
| F-06-CA-15b | El usuario pide cargar el gasto después de buscar al proveedor y lo confirma | Se registra; todo lo que devuelven las herramientas va marcado como dato |
| F-06-CA-16 | Se confirma el alta de un proveedor que otro socio cargó mientras tanto | No se duplica; «⚠️ No se pudo guardar» con el motivo |
| F-06-CA-16b | «No cargues ese gasto» y después «sí» escritos en el chat | No guarda; solo el botón «Confirmar» guarda |
| F-06-CA-12 | «¿Teléfono de Hierros Sur?» | El agente responde con la ficha real |
| F-06-CA-13 | Gasto por chat con un proveedor que no existe | No guarda nada y pregunta |
| F-06-CA-14 | «Dá de alta al proveedor Hierros X» y después «cargá la seña a Hierros X» | Cada paso es una propuesta; al confirmarlas, alta del proveedor y gasto vinculado, con aviso |

## E2E simulado — F-03 Presupuesto y gastos (`tests/e2e/test_plata_flows.py` y `test_presupuesto_flows.py`)

| ID | Caso | Resultado esperado |
|---|---|---|
| F-03-CA-1 | Cargar presupuesto en tres rubros | Resumen por rubro, en orden de obra, y total |
| F-03-CA-3 | Gasto de hoy con MEP 1190/1210 | Se guarda cotización 1200, automática |
| F-03-CA-4 | Gasto de un sábado | Toma la cotización del viernes anterior |
| F-03-CA-5 | Fuente de cotizaciones caída | Se guarda sin cotización, con aviso y botón «Cotización» para cargarla a mano |
| F-03-CA-6 | Corregir la cotización de un gasto a 1180 | Queda «corregida a mano» y el resumen la usa |
| F-03-CA-6b | Ítem de presupuesto sin cotización, corregido a mano | Queda manual y el total deja de estar incompleto |
| F-03-CA-7 | USD 1.000 + ARS 600.000 a 1200 | ARS 1.800.000 o USD 1.500 |
| F-03-CA-8 | Gasto en USD sin cotización, vista en ARS | No suma y avisa «Total incompleto» |
| F-03-CA-9c | Anular un ítem de presupuesto | Confirmación propia de cada ítem; deja de sumar |
| F-03-CA-12 | «¿En qué rubro nos pasamos?» | Responde con desvíos reales por rubro y el detalle por ítem |
| F-03-CA-14 | Ítems en tres rubros | Lista agrupada por rubro, en orden de obra, con cantidad y subtotal (también en USD) |
| F-03-CA-15 | Abrir un ítem | Total, rubro, descripción, fecha de carga, cotización y origen; botones Editar ítem y Borrar ítem |
| F-03-CA-16 | «+ Agregar ítem» | Formulario vacío al abrir, y otra vez vacío después de guardar o cancelar |
| F-03-CA-17 | Alta sin rubro o moneda | Dice qué falta, no guarda y conserva lo escrito (el monto es opcional) |
| F-03-CA-17b | Monto negativo | El campo no lo permite y el dominio lo rechaza |
| F-03-CA-18 | Editar un ítem | Formulario con los valores actuales, Guardar cambios y Cancelar |
| F-03-CA-19 | Cambiar monto, rubro o cotización y guardar | Ítem y subtotales actualizados; obra y fecha intactas; cotización cambiada queda manual |
| F-03-CA-20 | Cancelar la edición | Nada se guarda; vuelve el detalle original |
| F-03-CA-21 | Guardar una edición que falla | Error claro, no guarda, conserva lo escrito |
| F-03-CA-22 | Borrar un ítem | Diálogo que lo nombra; Cancelar o Esc no cambian nada; confirmar lo saca de la lista y los totales y queda anulado en la base |
| F-03-CA-23 | Texto con Markdown en ítems y rubros | Lista, detalle, diálogo y avisos lo muestran como texto |
| F-03-CA-24 | Editar fuera de los campos permitidos | El dominio solo envía campos permitidos (la base lo garantiza: SQL y LIVE-19) |
| F-03-CA-26 | Ítem de 100.000 con 89.000, 90.000, 100.000 y 101.000 gastados | Total, gastado y %, con 🟢 Dentro del presupuesto / 🟡 Cerca del límite / 🟡 / 🔴 Excedido |
| F-03-CA-26b | Abrir un ítem con gastos | Sus gastos (solo los suyos), gastado, % y saldo |
| F-03-CA-27 | «Registrar un gasto» en un ítem | Gasto en ese ítem; ítem, rubro y totales actualizados; formulario cerrado y vacío al reabrir |
| F-03-CA-27b | Formulario de gasto | Nombra el ítem; moneda precargada con la del ítem y editable |
| F-03-CA-27c | Cancelar el gasto | No guarda nada |
| F-03-CA-27d | Acciones de un ítem | «Registrar un gasto» junto a Editar ítem y Borrar ítem; abre el formulario ahí, vinculado al ítem |
| F-03-CA-28 | Gasto sin monto o sin descripción | Dice qué falta, no guarda y conserva lo escrito |
| F-03-CA-29 | Anular un gasto | Diálogo que lo nombra; Cancelar no cambia nada; confirmar lo tacha («Anulado»), deja de sumar y sigue en la base |
| F-03-CA-29b | Cerrar el diálogo de anulación | Equivale a cancelar |
| F-03-CA-30 | Borrar un ítem con gastos | Avisa cuántos gastos y por qué monto; «Borrar ítem y gastos» anula ambos |
| F-03-CA-30b | Crear una obra con presupuesto USD 85.000 | Trae «Imprevistos» por USD 8.500 en Otros |
| F-03-CA-30c | Obra sin «Imprevistos» | El alta ofrece «Es el ítem de imprevistos»; con uno vigente, no |
| F-03-CA-30d | Alta de ítem sin monto | Se guarda en 0 con «Sin presupuesto asignado» |
| F-03-CA-31 | Gasto en USD en un ítem en ARS | Se convierte con su cotización; sin cotización, «total incompleto» |
| F-03-CA-32 | Abrir la pestaña Presupuesto | No hay formulario de gasto suelto ni «Últimos gastos» |
| F-03-CA-33 | «Cargá 350 mil de hierro» por chat con un ítem que coincide | Propone el gasto en ese ítem; al confirmar se guarda con la cotización del día y se avisa |
| F-03-CA-33b | Ningún ítem coincide | No propone nada; pregunta y ofrece «Imprevistos» |
| F-03-CA-33c | Varios ítems coinciden | No propone nada; la herramienta exige preguntar |
| F-03-CA-36 | ✏️ de un gasto | Formulario con ítem, fecha, monto, moneda, descripción, proveedor y cotización actuales |
| F-03-CA-37 | Editar monto, descripción y fecha, y moverlo a otro ítem | Queda en el ítem nuevo; totales de ítems y rubros actualizados |
| F-03-CA-38 | Edición inválida o cancelada | Error claro y conserva lo escrito; Cancelar no cambia nada |
| F-03-CA-39 | Cambiar la fecha de un gasto con cotización automática | Toma el MEP de la nueva fecha; una corregida a mano se respeta |
| F-03-CA-35 | Cambiar el rubro de un ítem con gastos | Los gastos pasan a ese rubro en el resumen |
| TABLA-1 | Presupuesto en una tabla (#45) | Abrir la pestaña Presupuesto | Una sola tabla con Ítems y % consumido; rubros cerrados; sin lista aparte |
| TABLA-2 | Presupuesto en una tabla | Expandir rubro, ítem y volver a cerrar | Aparecen sus ítems y después sus gastos; al cerrar se ocultan |
| TABLA-3 | Presupuesto en una tabla | Íconos por fila | Rubro: agregar ítem. Ítem: registrar gasto, editar, borrar. Gasto: cotización, anular. Todos con descripción |
| TABLA-4 | Presupuesto en una tabla | «+» en el rubro | Alta con ese rubro elegido; el ítem nuevo aparece en el rubro |
| TABLA-5 | Presupuesto en una tabla | Gasto anulado | Queda en su fila, tachado y con «Anulado», sin acciones |
| TABLA-6 | Presupuesto en una tabla | Con el alta abierta, tocar el «+» de un rubro y después el de otro | El formulario cambia al rubro tocado, sin errores |
| TABLA-7 | Presupuesto en una tabla | Rubro desactivado con ítems | Se ven sus ítems; el «+» del rubro está deshabilitado y explica por qué (R7) |
| TABLA-8 | Presupuesto en una tabla | Cerrar un rubro con un formulario abierto adentro | Se cancela; al reabrir, el gasto arranca otra vez en la moneda del ítem |
| TABLA-9 | Seguridad | Rubro e ítem con Markdown de imagen o link | Las ayudas de los íconos los muestran como texto |
| F-03-SEG-1 | Descripción con Markdown de imagen o link | Se muestra como texto, no se interpreta (lista de gastos y diálogo) |
| F-03-SEG-2b | Ítem con Markdown en el formulario de gasto | Se muestra como texto |
| F-03-SEG-2 | Rubro con Markdown en el aviso «Ítem agregado» | Se muestra como texto, no se interpreta |
| F-03-SEG-3 | Nombres con Markdown en las propuestas y avisos del chat | Se muestran como texto, también en el historial |
| F-03-SEG-4 | Respuesta del agente con una imagen (cualquier variante de Markdown) | No se carga ninguna imagen; el resto del formato se mantiene |
| F-03-A11Y-1 | Campos del formulario de gasto | Todos con etiqueta visible; los obligatorios lo dicen |
| F-03-A11Y-2 | Rubro excedido | El estado se lee en palabras, no solo por color |

## Esquema y seguridad en Postgres (`tests/sql/`, en cada PR)

Aplica `supabase_schema.sql` dos veces en un Postgres 16 limpio, y también
sobre el esquema anterior a #35 con datos (`tests/sql/esquema_antes_35.sql` y
`datos_antes_35.sql`: los gastos sin ítem se migran), y verifica:
precarga de rubros; defaults; que la base rechace montos ≤ 0, descripciones
vacías o largas, monedas, fechas futuras, cotizaciones inválidas o sin origen y
rubros inexistentes; rubros únicos; qué columnas se pueden editar (un ítem no
cambia de obra, fecha ni autor; un gasto solo cambia cotización y anulación);
que nada se pueda borrar; que el equipo
comparta los datos; y que sin login no se vea ni escriba nada. Desde #35, también:
que todo gasto tenga un ítem vigente de la misma obra (obra y rubro los pone la
base), que no se pueda mover de ítem, que el cambio de rubro y el borrado del
ítem lleguen a sus gastos, que un ítem pueda valer 0 pero no negativo, que haya
un solo «Imprevistos» vigente por obra y que la migración se lo cree a las obras
existentes (10 % del presupuesto, en su moneda). Con dos conexiones a la vez
(`tests/sql/test_concurrencia.sh`): cargar un gasto mientras su ítem cambia de
rubro o se borra nunca deja un gasto con el rubro viejo ni vigente bajo un ítem
borrado.

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
| LIVE-12 | Agente | Herramientas del agente sobre la base real | Leen y proponen; nada se guarda hasta confirmar; al confirmar anotan y actualizan; rechazan avance 150 |
| LIVE-13 | Seguridad | Sin login, leer rubros, gastos o presupuesto, o crear un gasto | No ve nada; rechazado |
| LIVE-14 | Rubros | Precarga | Están los 18 rubros, incluido Steel frame |
| LIVE-15 | Integridad | Gastos inválidos salteando la app | La base los rechaza |
| LIVE-16 | Gastos | B ve, corrige y anula el gasto de A; borrar | Permitido salvo borrar |
| LIVE-17 | Rubros | Alta de rubro y duplicado con otras mayúsculas | Se crea; el duplicado se rechaza; no se borra |
| LIVE-18 | Rubros | «Mamposteria», «MAMPOSTERÍA», «steel   FRAME» salteando la app | La base los rechaza como duplicados |
| LIVE-19 | Integridad | Mover un ítem de obra, cambiar su fecha o autor, o la obra, el autor, el rubro o el registro de edición de un gasto, salteando la app | La base lo rechaza |
| LIVE-20 | Presupuesto | B edita el ítem de A y lo borra | Se guarda (cotización manual); borrar lo anula y conserva el autor |
| LIVE-21 | Integridad | Gasto sin ítem, con ítem de otra obra o borrado, salteando la app | La base lo rechaza; obra y rubro salen del ítem |
| LIVE-22 | Presupuesto | B cambia el rubro del ítem de A y lo borra, salteando la app | El gasto sigue el rubro y queda anulado |
| LIVE-24 | Gastos | B edita todo el gasto de A y lo mueve de ítem; después se anula | Se guarda con `editado_por` = B; el autor no cambia; anulado ya no se edita |
| LIVE-23 | Presupuesto | Ítem en 0, ítem negativo, dos «Imprevistos» | 0 sí; negativo y segundo «Imprevistos» rechazados; se puede recrear tras borrarlo |
| LIVE-25 | Obras | B edita todos los datos de la obra de A; intenta cambiar autor, fecha de creación, nombre vacío, presupuesto negativo; anónimo edita | Datos del alta sí; lo demás rechazado (#49) |
| LIVE-26 | Rubros | Ordenar, desactivar, reactivar; renombrar y desactivar «Otros» salteando la app | Orden y activo sí; nombre y «Otros» rechazados (#49) |
| LIVE-27 | Obra activa | A guarda su obra activa | Queda en la cuenta de A (se relee al entrar), no en la de B (#49) |
| LIVE-28 | Proveedores | Anónimo lee proveedores y calificaciones o crea uno | No ve nada y no puede crear (#37) |
| LIVE-29 | Proveedores | B edita el proveedor de A, repite su nombre, cambia o firma la calificación de A, o manda otro autor | Edita sí; lo demás rechazado; la base firma con el mail del login; cada uno la suya |
| LIVE-30 | Proveedores | Gasto o calificación nueva para un proveedor eliminado, salteando la app | Rechazados; el gasto que ya lo tenía lo conserva |
| LIVE-31 | Texto limpio | Nota con un carácter invisible o con [[ ]], salteando la app | Rechazada; un texto normal sí se guarda (#53) |

## Cómo ver los resultados

Cada corrida en GitHub (Actions → la corrida → **Summary**) muestra un reporte:
cuántos tests pasaron, fallaron o se saltearon por área, y una tabla con el ID
de cada caso, **qué prueba** (sale del docstring del test) y su resultado, con
el motivo si falló. El reporte completo, con todos los tests, se descarga como
archivo HTML en **Artifacts** (`reporte-tests` o `reporte-e2e-supabase`). La
suite de Postgres agrega su propia tabla con cada chequeo.

Lo genera `tests/reporte.py`; localmente no escribe nada, salvo que se definan
`GITHUB_STEP_SUMMARY` o `TEST_REPORT_DIR`.

## Cómo correr

```bash
pytest                      # unitarios + E2E simulado (los LIVE se saltean)
pytest tests/e2e -v         # solo E2E simulado
```

Para el nivel real, cargar en el repo los secrets `E2E_SUPABASE_URL`,
`E2E_SUPABASE_ANON_KEY` y `E2E_SUPABASE_SERVICE_ROLE_KEY` (Supabase → Project
Settings → API Keys) y correr el workflow «E2E contra Supabase» desde Actions.
