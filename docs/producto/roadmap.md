# Roadmap

| Orden | Ficha | Estado | Por qué en este orden |
|---|---|---|---|
| ✅ | [F-01 Consultas de normativa](funcionalidades/F-01-normativa.md) | Hecha | Base del agente |
| ✅ | [F-02 Tracker de obras y bitácora](funcionalidades/F-02-tracker-obras.md) | Hecha | La obra es la unidad central |
| ✅ | [F-03 Presupuesto y gastos](funcionalidades/F-03-presupuesto-gastos.md) | Hecha | Es lo que más impacta el negocio de flipping y crea la lista de **rubros** que usa F-04. Mejora #35: gastos dentro de cada ítem, «Imprevistos» y semáforo |
| ✅ | [UX-03 Menú y obra activa](funcionalidades/UX-03-navegacion-obra-activa.md) | Hecha | #49: menú a la izquierda, obra activa siempre visible y recordada, Detalle editable, Rubros; «Plata» pasa a «Presupuesto» |
| ✅ | [F-06 Proveedores](funcionalidades/F-06-proveedores.md) | Hecha | #37: lista compartida, ficha con compras y estrellas, proveedor elegido en cada gasto; base para las ofertas (#36) |
| ✅ | [SEG-01 Revisión de lo que se guarda](funcionalidades/SEG-01-sanidad.md) | Hecha | #53: limpieza y rechazo de órdenes para el agente al guardar, restricciones en la base, datos marcados al agente |
| ✅ | [F-03 · Ítems por unidad de medida](funcionalidades/F-03-presupuesto-gastos.md#mejora-ítems-por-unidad-de-medida-55) | Hecha | #55: cada ítem global o por unidad (m², caja…); total = cantidad × precio |
| 2 | [F-04 Etapas y cronograma](funcionalidades/F-04-etapas-cronograma.md) | Borrador | Reusa los rubros; con presupuesto cargado, el avance de la obra puede ponderarse por costo |
| 3 | [F-05 Fotos y documentos](funcionalidades/F-05-fotos-documentos.md) | Borrador | Agrega Storage; al llegar última puede vincular archivos a gastos y etapas desde el primer día |

**Cómo avanzar:** cada ficha se implementa en su propio PR, en este orden, solo
cuando está en `Lista` (sus *Decisiones pendientes* resueltas).

## Ideas sin ficha (backlog)

- Normativa de **Quilmes** y otros municipios (mejora de F-01).
- Archivar obras y editar notas (mejoras de F-02, #26). Editar los datos de la
  obra ya está, en su Detalle (UX-03).
- Unir proveedores duplicados (mejora de F-06).
- **Ofertas de proveedores por ítem** (#36), sobre la lista de F-06: candidata a F-07.
- Renombrar rubros (la pantalla de UX-03 agrega, ordena y desactiva).
- **Flujo de fondos** del flipping: ingresos, señas, aportes de socios y
  rentabilidad por obra. Decidido fuera de F-03 (D5); candidata a una ficha propia.
- Acceso de solo lectura para clientes o inversores (fuera de alcance en la
  [visión](vision.md) por ahora).
- Abrir el producto a otros estudios (Obra.AI): multiempresa, planes, facturación.
