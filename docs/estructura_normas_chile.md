# Estructura del Sistema Normativo Chileno

## Jerarquia de Normas

```
                    ┌─────────────────────────┐
                    │     CONSTITUCION        │
                    │  Norma suprema del      │
                    │  ordenamiento juridico  │
                    └───────────┬─────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            │                   │                   │
            ▼                   ▼                   ▼
   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
   │      LEY        │ │      DFL        │ │       DL        │
   │                 │ │ Decreto con     │ │  Decreto Ley    │
   │ Aprobada por    │ │ Fuerza de Ley   │ │ (solo periodos  │
   │ Congreso        │ │ (delegacion     │ │  de excepcion)  │
   │                 │ │  legislativa)   │ │                 │
   └────────┬────────┘ └─────────────────┘ └─────────────────┘
            │
            │ reglamenta
            ▼
   ┌─────────────────┐
   │    DECRETO      │
   │   SUPREMO (DS)  │
   │                 │
   │ Firmado por     │
   │ Presidente +    │
   │ Ministro        │
   └────────┬────────┘
            │
            │ implementa
            ▼
   ┌─────────────────┐
   │   RESOLUCION    │
   │                 │
   │ Emitida por     │
   │ organo tecnico  │
   │ (CNE, SEC, etc) │
   └─────────────────┘
```

---

## Tipos de Normas

### LEY
- **Que es**: Norma general aprobada por el Congreso Nacional
- **Numeracion**: Correlativa nacional (ej: Ley 20.936)
- **Ejemplo sector electrico**:
  - Ley 20.936 - Sistema de Transmision Electrica
  - Ley 19.940 - Ley Corta I
  - DFL 4/2006 - Ley General de Servicios Electricos (texto refundido)

### DECRETO SUPREMO (DS)
- **Que es**: Norma dictada por el Presidente de la Republica
- **Numeracion**: Se reinicia cada año, por ministerio
- **Identificacion completa**: "Decreto 62 de 2006 del Ministerio de Economia"
- **Variantes**:

```
┌──────────────────────────────────────────────────────────────────┐
│                    TIPOS DE DECRETO                              │
├──────────────────┬───────────────────────────────────────────────┤
│ DECRETO          │ Decreto supremo estandar                      │
│                  │ Requiere toma de razon por Contraloria        │
├──────────────────┼───────────────────────────────────────────────┤
│ DECRETO EXENTO   │ No requiere toma de razon                     │
│                  │ Materias menores o urgentes                   │
├──────────────────┼───────────────────────────────────────────────┤
│ DECRETO T        │ Sufijo "T" = Tarifario                        │
│                  │ Fija precios, peajes, tarifas                 │
│                  │ Ej: "Decreto 11 T" fija valor transmision     │
├──────────────────┼───────────────────────────────────────────────┤
│ REGLAMENTO       │ Decreto que reglamenta una ley                │
│                  │ Ej: D.62 reglamenta art.150 DFL 4             │
└──────────────────┴───────────────────────────────────────────────┘
```

### DFL (Decreto con Fuerza de Ley)
- **Que es**: Decreto dictado por el Presidente con autorizacion del Congreso
- **Tiene rango de ley**: Puede modificar o derogar leyes
- **Ejemplo clave**: DFL 4/2006 Min. Economia - Ley General de Servicios Electricos

### DL (Decreto Ley)
- **Que es**: Norma con rango de ley dictada sin Congreso
- **Solo en periodos de excepcion**: Gobierno militar 1973-1990
- **Ejemplo**: DL 2.224 de 1978 - Crea la CNE

### RESOLUCION
- **Que es**: Acto administrativo de un organo tecnico
- **Emitidas por**: CNE, SEC, Coordinador Electrico, Panel de Expertos
- **Variantes**:
  - RESOLUCION EXENTA: No requiere toma de razon
  - RESOLUCION AFECTA: Requiere toma de razon

---

## Numeracion de Decretos

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   DECRETO 62 de 2006 del MINISTERIO DE ECONOMIA                     │
│   ~~~~~~~~    ~~~~     ~~~~~~~~~~~~~~~~~~~~~~~~                     │
│      │         │                │                                   │
│      │         │                └── Ministerio que lo dicta         │
│      │         │                                                    │
│      │         └── Año de publicacion                               │
│      │                                                              │
│      └── Numero correlativo (se reinicia cada año por ministerio)   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

IMPORTANTE: El mismo numero puede existir en distintos ministerios y años

  Decreto 62 de 2006 Min. Economia  →  Transferencias de Potencia
  Decreto 62 de 2010 Min. Energia   →  Otra materia completamente distinta
```

---

## Organismos del Sector Electrico

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MINISTERIO DE ENERGIA                           │
│                     (Antes: Min. Economia)                          │
│                                                                     │
│   Rol: Politica energetica, dicta decretos supremos                 │
└─────────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
┌───────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│       CNE         │ │      SEC        │ │    COORDINADOR          │
│                   │ │                 │ │    ELECTRICO            │
│ Comision Nacional │ │Superintendencia │ │    NACIONAL             │
│ de Energia        │ │de Electricidad  │ │                         │
│                   │ │y Combustibles   │ │ (Antes: CDEC-SIC/SING)  │
│ Rol: Tarifas,     │ │                 │ │                         │
│ normas tecnicas,  │ │ Rol: Fiscalizar │ │ Rol: Operar el sistema, │
│ planificacion     │ │ seguridad       │ │ despacho economico      │
└───────────────────┘ └─────────────────┘ └─────────────────────────┘
                                                    │
                                                    ▼
                                          ┌─────────────────┐
                                          │     PANEL DE    │
                                          │    EXPERTOS     │
                                          │                 │
                                          │ Rol: Resolver   │
                                          │ discrepancias   │
                                          └─────────────────┘
```

---

## Relaciones entre Normas

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TIPOS DE RELACION                                │
├─────────────────┬───────────────────────────────────────────────────┤
│    MODIFICA     │ Cambia articulos de otra norma                    │
│                 │ La norma original sigue vigente (modificada)      │
├─────────────────┼───────────────────────────────────────────────────┤
│    DEROGA       │ Elimina otra norma completa                       │
│                 │ La norma derogada deja de existir                 │
├─────────────────┼───────────────────────────────────────────────────┤
│   REGLAMENTA    │ Desarrolla/implementa una ley                     │
│                 │ Ej: D.62 reglamenta art.150 del DFL 4             │
├─────────────────┼───────────────────────────────────────────────────┤
│   SUSTITUYE     │ Reemplaza texto especifico                        │
│                 │ "Sustituyese el articulo 3 por el siguiente..."   │
├─────────────────┼───────────────────────────────────────────────────┤
│    AGREGA       │ Añade contenido nuevo                             │
│                 │ "Agregase el siguiente articulo 5 bis..."         │
└─────────────────┴───────────────────────────────────────────────────┘
```

### Ejemplo de Cadena de Modificaciones

```
DFL 4/2006 (Ley General de Servicios Electricos)
    │
    │ reglamenta art. 150
    ▼
Decreto 62/2006 (Reglamento Transferencias de Potencia)
    │
    ├── modificado por ──► Decreto 44/2007
    │
    ├── modificado por ──► Decreto 42/2020
    │
    └── modificado por ──► Decreto 70/2024
```

---

## Estados de una Norma

```
┌─────────────┐
│   VIGENTE   │  La norma esta activa y produce efectos
└─────────────┘

┌─────────────┐
│ MODIFICADA  │  Vigente pero con cambios por otras normas
└─────────────┘

┌─────────────┐
│  DEROGADA   │  Ya no existe juridicamente
└─────────────┘
```

---

## Ejemplo Practico: Decreto 62

```
┌─────────────────────────────────────────────────────────────────────┐
│  DECRETO 62                                                         │
│  Ministerio de Economia, Fomento y Reconstruccion                   │
│  Publicacion: 01-FEB-2006                                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  TITULO: "Aprueba Reglamento de Transferencias de Potencia          │
│           entre Empresas Generadoras establecidas en la             │
│           Ley General de Servicios Electricos"                      │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  REGLAMENTA:  DFL 4/2006 (LGSE), articulo 150                       │
├─────────────────────────────────────────────────────────────────────┤
│  MODIFICADO POR:                                                    │
│    • Decreto 44/2007 - Ajustes menores                              │
│    • Decreto 42/2020 - Adapta a Ley 20.936                          │
│    • Decreto 70/2024 - Actualiza formulas                           │
├─────────────────────────────────────────────────────────────────────┤
│  ESTADO: VIGENTE (modificado)                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Materias del Sector Electrico (Clasificacion)

Las normas del sector electrico se clasifican en estas materias:

| Materia | Descripcion | Ejemplos |
|---------|-------------|----------|
| **Transmision Electrica** | Lineas, subestaciones, expansion | Ley 20.936, D.14T |
| **Generacion Electrica** | Centrales, potencia firme | D.62, D.52 |
| **Distribucion Electrica** | Redes BT/MT, concesionarias | D.327, NT Calidad |
| **Tarifas y Precios** | Precios nudo, peajes, VAD | D.11T, Res. CNE |
| **Energias Renovables** | ERNC, PMGD, net billing | Ley 20.257 |
| **Operacion del Sistema** | Despacho, coordinacion | Reglamento Coordinador |
| **Servicios Complementarios** | SSCC, frecuencia, reserva | NT SSCC |
| **Seguridad y Calidad** | Normas tecnicas, interrupciones | NT Calidad Servicio |
| **Institucionalidad** | CNE, SEC, Coordinador | DL 2.224, Ley 20.936 |
| **Concesiones** | Permisos, servidumbres | Titulo II DFL 4 |

---

## Referencias

- [BCN Ley Chile](https://www.bcn.cl/leychile) - Base de datos oficial
- [Coordinador Electrico Nacional](https://www.coordinador.cl) - Normativa tecnica
- [CNE](https://www.cne.cl) - Resoluciones y normas tecnicas
- [SEC](https://www.sec.cl) - Fiscalizacion y seguridad
