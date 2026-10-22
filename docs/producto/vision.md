# Visión

## En una frase

Atrium Agent es el **copiloto de obra** de Atrium: concentra en un solo lugar
las obras del equipo, su avance, su plata y sus papeles, y responde la
normativa aplicable a cada obra.

## Para quién (próximos 6 meses)

**Carolina y sus socios en Atrium.** Todos tienen los mismos permisos: cargan,
editan y consultan todas las obras. Usan la app sobre todo **desde el celular**,
a veces en la obra misma.

No hay usuarios externos en esta etapa: ni clientes, ni contratistas, ni
inversores.

## Problema que resuelve

Hoy la información de una obra está repartida entre planillas, chats,
fotos en el celular y PDFs de normativa. Cuesta responder rápido:

- ¿Cómo viene cada obra? ¿Está atrasada?
- ¿Cuánto llevamos gastado y contra qué presupuesto? ¿En pesos o en dólares?
- ¿Dónde está la foto de la platea o el plano aprobado?
- ¿Qué permite el código de edificación para *esta* obra?

## Estrategia: interna primero, producto después

Primero se usa en las obras propias de Atrium (flipping, construir para
vender, proyectos del estudio). Si funciona, puede abrirse a otros estudios
y constructoras (la idea Obra.AI).

**Qué implica para el diseño hoy:**

- Se optimiza para el equipo actual. **No** se construye nada multiempresa
  ni de facturación todavía.
- Pero tampoco se cierra la puerta: datos con dueño (`creado_por`), RLS en
  todas las tablas, nada «hardcodeado» a una obra o persona concreta, y
  la lógica de negocio separada de la interfaz.

## Principios

1. **Celular primero.** Cada pantalla tiene que usarse con una mano y en
   pantallas chicas. Formularios cortos.
2. **El chat es una vía de carga de primera.** Todo lo que se puede cargar
   en un formulario debería poder pedirse al agente («anotá…», «cargá un
   gasto de…»). El agente solo escribe cuando se le pide y avisa qué guardó.
3. **Datos reales, nunca inventados.** El agente responde con lo que hay en la
   base o en la normativa cargada; si no sabe, lo dice.
4. **ARS y USD conviven.** Toda cifra de plata tiene moneda. Nunca se suman
   monedas distintas sin un tipo de cambio explícito.
5. **Nada se borra por accidente.** Se prefiere anular o archivar a borrar.

## Fuera de alcance (por ahora)

- Portal o acceso para clientes, contratistas o inversores.
- Roles y permisos distintos dentro del equipo.
- Facturación, cobros, integración contable o con AFIP/ARCA.
- Cómputo métrico automático a partir de planos.
- App nativa (se usa la web en el celular).

## Cómo sabemos que funciona

- Todas las obras activas de Atrium están cargadas y se actualizan al menos
  una vez por semana.
- Se puede responder «¿cómo viene la obra X?» (avance, plata y última novedad)
  en menos de un minuto, desde el celular.
- Las consultas de normativa citan el código y la página.
