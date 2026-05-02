# Glosario curado — RAG Energy

Glosario de términos clave del dominio normativo eléctrico chileno, con **aliases propuestos** para que el sistema pueda expandir queries y matchear documentos cuando el usuario escribe variantes.

> **Cómo usar este glosario**
>
> - Cada entrada tiene la definición que ya está en la tabla `conceptos` de Postgres.
> - Los aliases NUEVOS (que NO están aún en la DB) están marcados con ➕.
> - Una vez revisados/aprobados por vos, se cargan a `conceptos.aliases` con un script de migración. El sistema los usa en query expansion automáticamente.
>
> **Estado de cada entrada:**
> - ✅ ya en DB con aliases
> - ⚠️ ya en DB, sin aliases — necesita curación
> - ❌ no existe en DB todavía — proponer crearlo

---

## 1. Instituciones y actores (acrónimos clave)

### Ministerio
- **Definición**: el Ministerio de Energía.
- **Refs**: 570 (#1 más referenciado)
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `Ministerio de Energía`
  - `MinEnergía`
  - `Ministerio del ramo`
- **Notas**: Cuando una norma dice solo "Ministerio" sin más, casi siempre es Energía.

### Comisión
- **Definición**: Comisión Nacional de Energía.
- **Refs**: 371
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `CNE`
  - `Comisión Nacional de Energía`
  - `la Comisión`
- **Notas**: "CNE" es la sigla universalmente usada por profesionales del rubro. **Crítico para query expansion** — usuarios casi siempre buscan "CNE" no "Comisión".

### Coordinador
- **Definición**: Coordinador independiente del sistema eléctrico nacional, al que se refiere el artículo 212º-1 de la Ley General de Servicios Eléctricos.
- **Refs**: 200
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `CEN`
  - `Coordinador Eléctrico Nacional`
  - `el Coordinador`
  - `Coordinador del Sistema`
- **Notas**: "CEN" es el acrónimo oficial. Misma criticidad que CNE.

### Superintendencia
- **Definición**: Superintendencia de Electricidad y Combustibles.
- **Refs**: 165
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `SEC`
  - `Superintendencia de Electricidad y Combustibles`
  - `la Superintendencia`
- **Notas**: "SEC" universal. Hay otra Superintendencia (Insolvencia y Reemprendimiento) que NO debe confundirse.

### Panel
- **Definición**: Panel de Expertos establecido en el Título VI del DFL N°4/20.018, de 2006...
- **Refs**: 38
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `Panel de Expertos`
  - `Panel de Expertos Eléctrico`

---

## 2. Sistemas eléctricos

### Sistema Eléctrico Nacional
- **Definición**: Sistema eléctrico interconectado cuya capacidad instalada de generación sea igual o superior a 200 megawatts.
- **Refs**: 30
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `SEN`
  - `Sistema Eléctrico Nacional Chileno`
- **Notas**: Antes existían el SIC (Sistema Interconectado Central) y el SING (Norte Grande); se fusionaron en el SEN en 2017. **Considerar agregar SIC/SING como aliases históricos** para queries sobre normas viejas.

### Sistema Eléctrico
- **Definición**: conjunto de instalaciones de centrales eléctricas generadoras, líneas de transporte, subestaciones eléctricas y líneas de distribución, interconectadas entre sí...
- **Refs**: 88
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `sistema eléctrico interconectado`
  - `red eléctrica`

### Sistema de Transmisión
- **Definición**: Conjunto de líneas y subestaciones eléctricas que forman parte de un sistema eléctrico y que no están destinadas a prestar el servicio público de distribución.
- **Refs**: 84
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `transmisión eléctrica`
  - `red de transmisión`

### Sistema de Transmisión Nacional
- **Definición**: Es aquel que permite la conformación de un mercado eléctrico común, interconectando los demás segmentos de transmisión...
- **Refs**: 24
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `STN`
  - `transmisión troncal` (terminología pre-2016)
  - `red troncal`
- **Notas**: Antes de la Ley 20.936 (2016) se llamaba "Sistema de Transmisión Troncal". Aliases histórico relevante.

### Sistemas de Transmisión Dedicados
- **Definición**: son aquellos que están constituidos por las líneas y subestaciones eléctricas radiales...
- **Refs**: 20
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `transmisión dedicada`
  - `STX`
  - `transmisión adicional` (pre-2016)

---

## 3. Tarifas y peajes (terminología técnica)

### C.O.M.A.
- **Definición**: Costo de Operación, Mantenimiento y Administración.
- **Refs**: en queries de eval
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `COMA` ← **muy importante**, sin puntos
  - `Costo de Operación, Mantenimiento y Administración`
  - `costo eficiente OMA`
  - `costos OMA`
- **Notas**: Usuarios típicos escriben "COMA" sin puntos. Sin alias, retrieval falla.

### V.A.T.T.
- **Definición**: Valor Anual de la Transmisión por Tramo.
- **Refs**: en queries de eval
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `VATT` ← **muy importante**
  - `Valor Anual de Transmisión por Tramo`
  - `Valor Anual del Tramo de Transmisión`
- **Notas**: Mismo patrón que C.O.M.A.

### AR
- **Definición**: Ajuste o recargo aplicable a los clientes.
- **Refs**: 14
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `Ajuste y Recargo`
  - `ajuste o recargo`
  - `ajustes tarifarios`
- **Notas**: ⚠️ "AR" es una sigla muy genérica. Considerar SI vale la pena expandirla — podría crear matches falsos. Recomendado **sólo expandir cuando el contexto sea tarifario**.

### PNEP
- **Definición**: Precio de nudo de la energía promedio para...
- **Refs**: 14
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `Precio de Nudo de la Energía Promedio`
  - `precio nudo energía`
  - `PNE promedio`

### PNPP
- **Definición**: Precio de nudo de la potencia de punta promedio.
- **Refs**: 14
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `Precio de Nudo de Potencia de Punta Promedio`
  - `precio nudo potencia`
  - `PNP promedio`

### Cargos por Suministro Eléctrico
- **Definición**: Cargos tarifarios correspondientes a las distintas opciones tarifarias...
- **Refs**: 13
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `cargos tarifarios`
  - `cargos por suministro`
  - `tarifa eléctrica`

### Cuenta de Tarifas o Peajes
- **Definición**: cantidades adeudadas por el Usuario de Sistema Interoperable por concepto de Tarifas o Peajes...
- **Refs**: 13+
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `cuenta de cobro`
  - `factura de peaje`
  - `cobro tarifa`

---

## 4. Potencia y generación

### Potencia de Suficiencia
- **Definición**: Potencia que una Unidad Generadora o Sistema de Almacenamiento de Energía aporta a la Suficiencia de Potencia del sistema o subsistema.
- **Refs**: 26
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `potencia firme` ← **importante (sinónimo histórico)**
  - `potencia inicial` ← terminología muy antigua, aún usada en consultas
  - `potencia eficiente`
- **Notas**: ⚠️ **Caso clave**: la query "qué es potencia inicial" en eval falló porque DB tiene "Potencia de Suficiencia" sin estos aliases. Curarlo subiría grounding directamente.

### Potencia Máxima
- **Definición**: Máximo valor que puede sostener de manera continua una Unidad Generadora...
- **Refs**: 18
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `potencia nominal`
  - `Pmax`
  - `capacidad nominal`

### Capacidad Instalada
- **Definición**: Suma de la potencia máxima de las unidades de generación que conforman el equipamiento de generación de un usuario final, expresada en kilowatts.
- **Refs**: 34
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `potencia instalada`
  - `kW instalados`
  - `capacidad nominal del parque`

### Capacidad Instalada Permitida
- **Definición**: Cálculo de la capacidad del equipamiento de generación máxima que puede conectar un usuario final en un punto de conexión...
- **Refs**: 13
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `capacidad permitida`
  - `límite de capacidad de conexión`

### Capacidad de Inyección
- **Definición**: Suma de la potencia máxima que el equipamiento de generación es capaz de inyectar a la red, expresada en kilowatts.
- **Refs**: 14
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `potencia de inyección`
  - `inyección máxima`

### Estado Deteriorado
- **Definición**: Condición de operación de una Unidad Generadora o Sistema de Almacenamiento de Energía en la cual se limita su Potencia Máxima...
- **Refs**: en queries de eval
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `condición deteriorada`
  - `derate`
  - `operación restringida`
- **Notas**: query falló en eval. Curarlo ayuda.

---

## 5. Distribución y empalme

### Empresa distribuidora
- **Definición**: la entidad que presta el servicio de gas mediante redes de distribución de gas, con o sin concesión.
- **Refs**: 62
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `distribuidora`
  - `concesionaria de distribución`
  - `empresa concesionaria`
- **Notas**: ⚠️ La definición en DB es del sector gas. **Hay que verificar** que también aplique a eléctrica, o crear un concepto separado para "Empresa distribuidora eléctrica".

### Empalme
- **Definición**: conjunto de tuberías y accesorios que conducen el gas...
- **Refs**: 16
- ⚠️ Definición del sector gas; verificar para eléctrico
- **Aliases propuestos** ➕:
  - `empalme eléctrico` (en contexto eléctrico)
  - `conexión a la red`

### Equipamiento de Generación Conjunto
- **Definición**: Equipamiento de Generación del que disponen dos o más usuarios finales conectados a la misma red de distribución...
- **Refs**: 24
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `generación conjunta`
  - `generación compartida`
  - `equipamiento conjunto`

### Adecuaciones
- **Definición**: Obras físicas y trabajos en el punto de conexión de un equipamiento de generación a la red de distribución eléctrica...
- **Refs**: 31
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `obras de adecuación`
  - `adecuaciones de conexión`

### Obras Adicionales
- **Definición**: Obras físicas mayores y trabajos en la red de distribución eléctrica, necesarias para la conexión de un Equipamiento de Generación.
- **Refs**: 22
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `obras adicionales de conexión`
  - `obras complementarias`

### Inyección de Excedentes Permitida
- **Definición**: Cálculo de la inyección máxima de potencia que el Equipamiento de Generación puede realizar en régimen permanente...
- **Refs**: 13
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `IEP`
  - `inyección permitida`
  - `límite de inyección`

---

## 6. Planificación y licitación

### Plan de Expansión
- **Definición**: Resultado del Proceso de Planificación de la Transmisión...
- **Refs**: 50
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `Plan de Expansión de la Transmisión`
  - `PdE`
  - `plan anual de expansión`

### Bases de Licitación
- **Definición**: Conjunto de normas y especificaciones administrativas, técnicas y económicas...
- **Refs**: 72
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `BL`
  - `bases de licitación pública`
  - `bases administrativas`
- **Notas**: ⚠️ Definición en DB es del sector concesiones viales (MOP). En contexto eléctrico significa "bases de licitación de suministro" — verificar.

---

## 7. Concursal (Ley 20.720)

### Persona Relacionada
- **Definición**: Se considerarán Personas Relacionadas respecto de una o más personas o de sus representantes, las siguientes:...
- **Refs**: en queries de eval (falló)
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `personas relacionadas`
  - `partes relacionadas`
- **Notas**: ⚠️ Término **homónimo** entre derecho concursal y derecho civil/familia. Ambiguo sin contexto. **Considerar metadata `dominio: concursal`** para disambiguación.

### Procedimiento Concursal
- **Definición**: cualquiera de los regulados en esta ley...
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `proceso concursal`
  - `quiebra` (terminología pre-2014)
  - `concurso de acreedores`

### Liquidador
- **Definición**: Aquella persona natural sujeta a la fiscalización de la Superintendencia de Insolvencia y Reemprendimiento...
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `Liquidador Concursal`
  - `síndico` (terminología antigua, pre-2014)

### Veedor / Informe del Veedor
- **Definición**: Aquel relativo al Acuerdo de Reorganización Judicial...
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `el Veedor`

### Quórum (Calificado / Especial / Simple)
- ⚠️ Distintos conceptos en DB
- **Aliases propuestos** ➕ (para el genérico "Quórum"):
  - `mayoría calificada`
  - `mayoría especial`
- **Notas**: Hay 3 tipos de quórum (calificado, especial, simple) en la ley 20.720. **Crear un concepto-padre "Quórum"** que apunte a los 3.

### Audiencia Inicial
- **Definición**: Aquella que se lleva a cabo en el tribunal competente con presencia del Deudor...
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `audiencia de inicio`
  - `audiencia primera`

### Deudor
- **Definición**: Toda Empresa Deudora o Persona Deudora...
- **Refs**: 30
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `el Deudor`
- **Notas**: Genérico, contexto concursal.

---

## 8. Generación renovable / biomasa

### Biomasa
- **Definición**: la materia orgánica sólida, biodegradable, de origen vegetal o animal...
- **Refs**: 13
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `biomasa sólida`
  - `materia orgánica energética`

### Biocombustibles sólidos
- **Definición**: combustibles elaborados a partir de biomasa de origen leñoso o no leñoso, tales como leña, pellets, carbón vegetal, briquetas y astillas, entre otros.
- **Refs**: 15
- ⚠️ Sin aliases en DB
- **Aliases propuestos** ➕:
  - `pellets`
  - `leña`
  - `briquetas`
  - `combustibles sólidos`

---

## 9. Tránsito (NO eléctrico — verificar relevancia)

> ⚠️ **Estos conceptos parecen ser del Reglamento del Tránsito**, no del rubro eléctrico. Probablemente vienen de una norma cargada por error o de glosarios mezclados. **Decisión a tomar:** ¿Se mantienen, se borran, o se filtran del retrieval?

- Vehículo (refs=152)
- Tránsito (refs=125)
- Conductor (refs=95)
- Calzada (refs=24)
- Detención (refs=20)
- Cruce (refs=18)
- Placa patente (refs=25)

---

## 10. Términos que necesitan revisión / curación profunda

### "Empalme" y "Medidor"
Definidas en DB con redacción del sector gas. Verificar si aplican también al eléctrico o crear conceptos separados.

### "Bases de Licitación"
Definida con redacción del sector concesiones viales (MOP). Probablemente hay una versión específica para el sector eléctrico (licitaciones de suministro de la CNE).

### Acrónimos genéricos peligrosos
- `AR` (Ajuste y Recargo) — tan corto que matchearía falsos positivos
- `MR` `IEP` `PNEP` `PNPP` — más específicos, OK

---

## Próximos pasos sugeridos

### Acción inmediata (alta-prioridad)
1. **Curar manualmente este archivo** — vos revisás aliases, marcás OK / corregís / descartás.
2. Importar aliases aprobados a la DB:
   ```sql
   UPDATE conceptos SET aliases = ARRAY['CNE', 'Comisión Nacional de Energía']
   WHERE nombre = 'Comisión';
   ```
3. Modificar `extract_query_concepts()` para usar aliases con full-text matching (no solo nombre exacto).

### Acción mediana (después)
- Importar glosarios oficiales:
  - Glosario CNE (Comisión Nacional de Energía)
  - Glosario SEC
  - Diccionario Coordinador Eléctrico Nacional
- Crear concepto-padre con `metadata.dominio` para desambiguación (concursal vs civil, gas vs eléctrico, etc.)
- Limpiar conceptos del Reglamento del Tránsito si no son relevantes.

### Esperado tras curación
- **Recall@5**: 95.8% → ~98%
- **Grounding pass**: 70.8% → 75-80% (las queries que fallaban por términos no encontrados ahora matchearían)
- **Cobertura por sigla**: usuarios podrían escribir "CNE", "SEC", "CEN", "SEN", "VATT", "COMA" y matchear correctamente.
