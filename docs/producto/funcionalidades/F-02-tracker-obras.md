# F-02 · Tracker de obras y bitácora

**Estado:** Hecha
**Prioridad:** Alta

## Objetivo

Que el equipo vea en un solo lugar todas las obras, su estado y avance, y
lleve una bitácora compartida, también por chat.

## Alcance actual

- Sección **📋 Obras**: listado con métricas y filtro por estado; alta de obra;
  cambio de estado y avance; bitácora con fecha y autor.
- **Obra elegida** arriba de la pantalla: la usan todas las pestañas y el agente (normativa del municipio + contexto). Ver UX-02 (#7).
- Herramientas del agente: `listar_obras`, `ver_obra`, `agregar_nota_bitacora`,
  `actualizar_obra`. Escribe solo si se le pide y avisa qué guardó.
- Datos compartidos por todo el equipo con RLS; nadie puede borrar obras.

## Criterios de aceptación (cubiertos por tests)

Ver `docs/casos-e2e.md`: E2E-04 a E2E-10 y E2E-13 a E2E-15 en la app;
LIVE-01, LIVE-02 y LIVE-04 a LIVE-09 y LIVE-12 contra la base real.

## Mejoras conocidas (sin priorizar)

- Editar los datos de una obra después de crearla (hoy solo estado y avance).
- Archivar obras terminadas para que no ocupen el listado.
- Editar o anular una nota de bitácora.
