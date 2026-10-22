# Definición de producto — Atrium Studio

Esta carpeta es la fuente de verdad sobre **qué** construimos y **por qué**.
El **cómo** técnico está en [`CLAUDE.md`](../../CLAUDE.md).

| Archivo | Qué responde |
|---|---|
| [`vision.md`](vision.md) | Para quién es, qué problema resuelve, qué queda afuera |
| [`glosario.md`](glosario.md) | Qué significa cada término del dominio, y su nombre en el código |
| [`roadmap.md`](roadmap.md) | Qué está hecho, qué sigue y en qué orden |
| [`funcionalidades/`](funcionalidades/) | Una ficha por funcionalidad, con criterios de aceptación |
| [`plantilla-funcionalidad.md`](plantilla-funcionalidad.md) | Molde para fichas nuevas |

## Cómo se usa

1. **Una idea nueva** → copiar la plantilla en `funcionalidades/F-XX-nombre.md`
   con estado `Borrador`. Alcanza con el objetivo y un par de criterios.
2. **Antes de codear** → completar las *Decisiones pendientes* y pasar la
   ficha a `Lista`. Claude no implementa fichas en `Borrador`.
3. **Al codear** → cada criterio de aceptación (`F-XX-CA-n`) se convierte en al
   menos un test E2E con ese ID en el docstring.
4. **Al terminar** → la ficha pasa a `Hecha` y el roadmap se actualiza en el mismo PR.

## Cómo pedirle algo a Claude

> «Implementá F-03» · «Agregá a F-04 un criterio para…» · «Escribí la ficha de
> esta idea: …» · «¿Qué decisiones faltan para que F-05 esté lista?»

Si un pedido contradice una ficha, Claude lo señala antes de codear y propone
actualizar la ficha en el mismo PR.
