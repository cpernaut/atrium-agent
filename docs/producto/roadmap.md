# Roadmap

| Orden | Ficha | Estado | Por qué en este orden |
|---|---|---|---|
| ✅ | [F-01 Consultas de normativa](funcionalidades/F-01-normativa.md) | Hecha | Base del agente |
| ✅ | [F-02 Tracker de obras y bitácora](funcionalidades/F-02-tracker-obras.md) | Hecha | La obra es la unidad central |
| 1 | [F-03 Presupuesto y gastos](funcionalidades/F-03-presupuesto-gastos.md) | **Lista** | Es lo que más impacta el negocio de flipping y crea la lista de **rubros** que usa F-04 |
| 2 | [F-04 Etapas y cronograma](funcionalidades/F-04-etapas-cronograma.md) | Borrador | Reusa los rubros; con presupuesto cargado, el avance de la obra puede ponderarse por costo |
| 3 | [F-05 Fotos y documentos](funcionalidades/F-05-fotos-documentos.md) | Borrador | Agrega Storage; al llegar última puede vincular archivos a gastos y etapas desde el primer día |

**Cómo avanzar:** cada ficha se implementa en su propio PR, en este orden, solo
cuando está en `Lista` (sus *Decisiones pendientes* resueltas).

## Ideas sin ficha (backlog)

- Normativa de **Quilmes** y otros municipios (mejora de F-01).
- Editar datos de una obra, archivar obras y editar notas (mejoras de F-02).
- **Flujo de fondos** del flipping: ingresos, señas, aportes de socios y
  rentabilidad por obra. Decidido fuera de F-03 (D5); candidata a F-06.
- Acceso de solo lectura para clientes o inversores (fuera de alcance en la
  [visión](vision.md) por ahora).
- Abrir el producto a otros estudios (Obra.AI): multiempresa, planes, facturación.
