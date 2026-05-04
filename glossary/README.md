# Glossary system

Source-of-truth for domain terms in the Chilean electrical regulation RAG.

## Files

| File | Purpose |
|---|---|
| `concepts.yaml` | The data — all concepts with definitions, aliases, sources, validation status |
| `schema.yaml` | Schema documentation for `concepts.yaml` (what each field means) |
| `incoming/*.yaml` | Per-norm extraction templates (workflow: extract → review → merge) |

## Workflow

### 1. Edit YAML directly (manual curation)

Open `concepts.yaml`, find the concept by name, edit:

```yaml
- name: "Comisión"
  aliases:
    - alias: "CNE"
      confidence: high       # high | medium | low
      validated: true        # ← flip to true after review
  status: ok                 # not_reviewed | ok | corrected | needs_research
  notes: "Universal acronym in the industry"
```

### 2. Render human-readable view

```bash
python scripts/render_glossary.py
# → updates docs/glossary.md (auto-generated, do NOT edit by hand)
```

### 3. Load aliases to Postgres

```bash
python scripts/load_glossary_to_db.py [--dry-run]
# → updates conceptos.aliases for entries with status=ok
# Only loads aliases marked validated: true
```

### 4. Incremental: bootstrap a new norm

When ingesting a new BCN norm:

```bash
python scripts/extract_glossary_template.py NORMA_ID
# → creates glossary/incoming/NORMA_ID.yaml with concepts auto-detected
```

Then review the YAML, mark validated, and merge:

```bash
python scripts/merge_glossary.py NORMA_ID  # (TODO)
# → moves YAML entries into concepts.yaml
```

## Field reference

See `schema.yaml` for full schema documentation.

Key fields:

- **`status`**: `not_reviewed` (default for auto-extracted), `ok` (validated), `corrected` (you fixed), `needs_research` (ambiguous, defer)
- **`aliases[].validated`**: Only `true` aliases get loaded to DB. `false` = proposed but not vetted.
- **`source.norm_id`**: BCN idNorma from where the definition was extracted.
- **`domain_context`**: For disambiguation when a term means different things in different domains (e.g. "Persona Relacionada" in concursal vs. civil).
- **`extraction_difficulty`**: Notes for future scrapers — what made this term hard to extract or define.

## Why YAML?

- Human-readable for manual curation
- Supports comments
- Git-friendly diffs
- Loadable programmatically
- Standard practice in HuggingFace / spaCy / NLP projects

## Standards inspiration

The schema is inspired by [SKOS](https://www.w3.org/TR/skos-reference/) (Simple Knowledge Organization System, W3C) but simplified:

| SKOS | Our schema |
|---|---|
| `prefLabel` | `name` |
| `altLabel` | `aliases[].alias` |
| `definition` | `definition` |
| `broader` | `relations.broader` |
| `narrower` | `relations.narrower` |
| `related` | `relations.related` |

Plus additional fields specific to legal RAG: `source` (provenance), `domain_context` (disambiguation), `status` (review state), `extraction_difficulty` (operational notes).
