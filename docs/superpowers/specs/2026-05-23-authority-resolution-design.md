# Resolución de autoridad (B1) — Design Spec

Fecha: 2026-05-23 · Sub-proyecto de resolución de entidades (sección A del roadmap GraphRAG).

> Alcance **B1 mínimo determinista**. Elige la definición autoritativa de un
> término definido en >1 norma por **rango → fecha → flag-conflicto**, y corrige
> el ground-truth del eval (hoy ingenuo de autoridad). DIFIERE ámbito, derogación
> y UX de ambigüedad a specs propios (ver §9). Bases verificadas en memoria
> [[reference_chilean_norm_hierarchy]] y handoff-2026-05-20 (addenda 2026-05-23).

## 1. Problema

Un término puede estar definido en varias normas (28 conceptos hoy). El sistema
elige por **fecha** solamente (lex posterior) → a veces cita la fuente equivocada.
Peor: para "qué es SEC" el sistema ya cita la **Ley 18410** (más autoritativa),
pero el **eval espera el glosario del decreto** → nuestro propio ground-truth es
ingenuo de autoridad. B1 arregla el sistema **y** el eval.

## 2. Jerarquía (verificada — CPR art. 64, CC 52-53)

`LEY ≡ DFL ≡ DL (rango legal) > DECRETO/DS > RESOLUCIÓN`
- DFL y DL = **mismo rango que LEY** (no debajo). Empates de mismo rango → fecha
  (lex posterior); si persiste → **conflicto** (no adivinar).
- **El `tipo` de la DB NO es confiable** (mislabels reales: "RESOLUCION" con
  tipo=LEY, DL con tipo="Ley"). → derivar rango del **TÍTULO**.

## 3. Componentes (archivos)

| archivo | responsabilidad |
|---|---|
| `src/extraction/norm_rank.py` (NUEVO, puro) | `derive_rank(tipo, titulo) -> (rank:int, flagged:bool)`. Parsea título: "DECRETO LEY"/"DFL"/"fuerza de ley"→rango legal; "RESOLUCION"→bajo; refundido conserva el rango de lo que consolida. Mapea LEY/DFL/DL=3, DECRETO=2, RESOLUCIÓN=1. `flagged=True` si tipo y título discrepan o el rango no es derivable. |
| `src/extraction/authority.py` (NUEVO, puro) | `select_authoritative(cands) -> dict`. `cands` = lista de `{id_norma, articulo, rank, fecha}`. Regla: mayor rank → fecha más reciente (NULLS last) → si empata en rank+fecha, `{"status":"conflict", ...}`; si gana uno, `{"status":"resolved", "id_norma", "articulo"}`. Sin derogación ni ámbito. |
| `scripts/resolve_authority.py` (NUEVO) | Sobre cada concepto con `define_termino` en >1 norma: arma candidatos, llama `select_authoritative`, guarda `conceptos.metadata.authoritative={id_norma,articulo}` (o `conflict=true` + lista). Idempotente (`metadata.authority_resolved`). `--apply`. Corre en ingesta tras `canonicalize_concepts`. |
| `src/pipelines/concept_injection.py` (MODIFICAR) | Cuando un concepto tiene `metadata.authoritative`, el inject usa ESE artículo (en vez de la regla de fecha del `_concept_index`). Conflicto → no fuerza (se resolverá en B3). |
| `scripts/build_eval_balanced.py` (MODIFICAR) | `expected_norma/articulo` por autoridad (no fecha) → corrige el gold ingenuo. Regenerar el set y re-medir cita_ok. |

## 4. Flujo de datos

```
norma (tipo, titulo, fecha) ──derive_rank──▶ rank
conceptos con define_termino en >1 norma
        │  candidatos {norma, art, rank, fecha}
        ▼
   select_authoritative ──resolved──▶ metadata.authoritative={norma,art}
        └────────────────conflict──▶ metadata.authority_conflict=[...]
        │
        ▼
inject usa metadata.authoritative · eval gold usa autoridad · re-medir
```

## 5. Incrementalidad (requisito del usuario)

`resolve_authority.py` corre **en la ingesta de cada norma nueva** y re-resuelve
los conceptos afectados: si una ley nueva define un término ya definido, gana por
rango/fecha sola. Cadena de ingesta: `extraer → build_definitions_auto →
canonicalize_concepts (A) → resolve_authority (B1) → [medir]`. Todo idempotente.

## 6. Legal-safety

- Rango y selección son **deterministas** (parse de título + comparación rank/fecha).
- Sin fuzzy. Conflictos no se adivinan → se marcan.
- Mislabels de `tipo` → flag, no asunción silenciosa.

## 7. Errores / edge cases

- Norma sin fecha → NULLS last (pierde el desempate por fecha, no rompe).
- Rango no derivable del título → `flagged`, va a revisión, no se auto-resuelve.
- 0 candidatos / 1 candidato → trivial (ese gana).
- Empate rank+fecha → `conflict` (B3 lo mostrará; hoy el inject no fuerza).

## 8. Tests

- `norm_rank`: DFL→legal, "DECRETO LEY"→legal, RESOLUCIÓN→bajo, refundido conserva
  rango, mislabel (tipo=LEY pero título "RESOLUCION") → flagged.
- `authority`: rango gana a fecha; "Ministerio" (LEY 1183783 vs DECRETOs) → gana
  LEY; empate rank+fecha → conflict; un solo candidato → resolved.
- Integración (DB): tras `--apply`, los 28 multi-definidos tienen `authoritative`
  o `conflict`; "qué es SEC"/"Superintendencia…" expected pasa a la Ley → cita_ok sube.

## 9. Diferido (specs propios, en el roadmap)

- **B2 — derogación/vigencia**: fetch BCN `obtxml?opt=7&idNorma=` (`derogado`+
  `FechaDerogacion`) + parse textual (175 "Reemplázase", 24 "Derógase") → excluir
  derogadas ANTES del rango. Mayoría apunta fuera del corpus (bajo ROI) → medir.
- **B-ámbito — lex specialis**: derivar ámbito por norma (clase/organismo/título)
  para desempatar por dominio. Corpus casi todo energía → rara vez desempata hoy.
- **B3 — UX de ambigüedad**: query palabra-suelta que matchea varios → mostrar
  opciones y pedir precisar (no sesgar por posición).

## 10. No-objetivos (YAGNI)

- No derogación, no ámbito, no UX de ambigüedad en B1.
- No tocar GraphRAG (preservado en el roadmap).
- No aplicar la cola de revisión de A (sub-proyecto F).
