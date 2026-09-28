"""Advanced concept extraction from article corpus with LLM validation.

Pipeline:
  1. Apply 5 detection regex (acronyms, definitions, paren-pairs, multi-word, refs)
  2. Filter heavy-noise candidates with rules (stopwords, fragments, dispersion)
  3. Validate surviving candidates with qwen3.5:9b using JSON schema
  4. Write `glossary/incoming/auto-extracted-clean.yaml` with status=not_reviewed

Each candidate gets a `confidence` from the LLM (high|medium|low|reject).
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.components.vectorstore import with_connection
from psycopg.rows import dict_row

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3.5:9b"

# === Filter dictionaries ===

# Common-word filter: tokens that match acronym pattern but aren't real acronyms
NOISE_TOKENS = {
    # Roman numerals
    "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
    "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    # Months / days abbreviations
    "ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "SEPT",
    "OCT", "NOV", "DIC", "LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM",
    # Spanish prepositions / articles wrongly capitalized
    "EL", "LA", "LOS", "LAS", "DE", "DEL", "EN", "POR", "Y", "O", "U",
    "QUE", "PARA", "CON", "SIN", "AL", "SE", "ES", "SU", "MÁS",
    # Legal-document structural words (often appear ALL-CAPS as section labels)
    "ART", "ARTÍCULO", "ARTICULO", "ARTICULOS", "ARTÍCULOS", "ARTS",
    "INC", "LETRA", "NUM", "CAPÍTULO", "CAPITULO", "TÍTULO", "TITULO",
    "PÁRRAFO", "PARRAFO", "ANEXO",
    "PRIMERO", "SEGUNDO", "TERCERO", "CUARTO", "QUINTO", "SEXTO", "SEPTIMO",
    "OCTAVO", "NOVENO", "DECIMO",
    "ANTERIOR", "SIGUIENTE", "PRESENTE", "RESPECTIVO",
    # Generic legal fillers
    "LEY", "DECRETO", "DFL", "DS", "DTO", "RES", "NORMA", "ORD",
    "NOTA", "REF", "VER",
    # First names / surnames of Chilean presidents that appear in signatures
    "GABRIEL", "BORIC", "FONT",  # Gabriel Boric Font
    "MICHELLE", "BACHELET", "JERIA",  # Michelle Bachelet Jeria
    "SEBASTIAN", "SEBASTIÁN", "PIÑERA", "ECHENIQUE",  # Sebastián Piñera Echenique
    "RICARDO", "LAGOS", "ESCOBAR",  # Ricardo Lagos Escobar
    "EDUARDO", "FREI", "RUIZ-TAGLE",  # Eduardo Frei Ruiz-Tagle
    "PATRICIO", "AYLWIN",  # Patricio Aylwin Azócar
    "SALVADOR", "ALLENDE",  # Salvador Allende Gossens
    # Common Chilean ministers' names (frequent in signatures)
    "DIEGO", "PARDOW", "JUAN", "CARLOS", "JOSÉ", "MARÍA",
    # Common foreign org acronyms not relevant
    "BLS", "USA", "EU", "UE", "OECD", "OCDE", "FMI", "IMF",
    # Currency / stats codes
    "USD", "CLP", "EUR", "DOL", "EUR", "GBP",
    # Common Spanish nouns that match the regex when ALL-CAPS in a heading
    "PAGO", "BORDE", "FECHA", "AVI", "PEAJE", "PEAJES",
    "POTENCIA", "ENERGIA", "ENERGÍA", "TENSIÓN", "TENSION",
    "SISTEMA", "SISTEMAS", "REDES", "RED",
    "INSTALACIONES", "INSTALACIÓN",
    "DECRETOS", "LEYES", "REGLAMENTO", "REGLAMENTOS",
    "PROCEDIMIENTO", "PROCEDIMIENTOS",
    # Often appear from "ART. NN" parsing
    "DICIEMBRE", "ENERO", "FEBRERO", "MARZO", "ABRIL",
    # Specific ALL-CAPS noise from previous run
    "EUS",  # often from "EU's" or fragments
    "DP", "DO", "NC",  # too generic, not concepts
    "AVI", "TSIC",  # fragments
}

# Spanish month/day full names
NOISE_FULLNAMES = {
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
    "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo",
    # President names
    "Gabriel Boric Font", "Sebastián Piñera", "Michelle Bachelet",
    "Ricardo Lagos", "Salvador Allende",
}

# Stopwords for the start of multi-word phrases (drop if first word is one of these)
PHRASE_BAD_FIRST = {
    "Lo", "La", "El", "Los", "Las", "Un", "Una", "Esta", "Este", "Estos",
    "Aquel", "Aquellos", "Este", "Por", "Para", "Con", "Sin",
    "Diario", "Boletín", "Visto", "Considerando", "Decreto", "Ley",
    "Artículo", "Capítulo", "Título", "Párrafo",
    "Don", "Doña", "Señor", "Señora",
    "Bureau", "Labor",  # often appears in foreign-org references
}


# === Detection regex ===

ACRONYM_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{1,7})\b")

DEF_PATTERNS = [
    re.compile(r"se\s+entender[áa]\s+por\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñ\s]{2,40}?)\s+(?:a|al|el|la|los|las|aquell)", re.IGNORECASE),
    re.compile(r"se\s+denominar[áa]\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñ\s]{2,40}?)(?:\.|,|;)", re.IGNORECASE),
    re.compile(r"(?:el|la|los|las)\s+([A-ZÁÉÍÓÚÑ][\w\sáéíóúñ]{2,40}?)\s+(?:corresponde|consiste|significa)", re.IGNORECASE),
    re.compile(r"denominad[oa]s?\s+([A-ZÁÉÍÓÚÑ][\w\sáéíóúñ]{2,40}?)(?:\.|,|;|\s+a)", re.IGNORECASE),
    re.compile(r"llamad[oa]s?\s+([A-ZÁÉÍÓÚÑ][\w\sáéíóúñ]{2,40}?)(?:\.|,|;)", re.IGNORECASE),
    re.compile(r"se\s+considerar[áa]\s+([A-ZÁÉÍÓÚÑ][\w\sáéíóúñ]{2,40}?)\s+(?:a|al|el|la|los|las|como)", re.IGNORECASE),
    re.compile(r"para\s+los\s+efectos\s+de\s+(?:este|el)\s+(?:reglamento|decreto|ley)\s*,?\s*se\s+entiende\s+por\s+([A-ZÁÉÍÓÚÑ][\w\sáéíóúñ]{2,40}?)\s+", re.IGNORECASE),
]

PAREN_PAIR_PATTERN = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+(?:de|del|en|y|o|para|por|a|al|con|sin)?\s*[A-ZÁÉÍÓÚÑa-záéíóúñ]+){0,8})\s*\(([A-Z][A-Z0-9\.]{1,7})\)"
)

PHRASE_PATTERN = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+(?:de|del|de la|de los|en|y|o|para|por|a|al)?\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+){1,4})\b"
)

# Match incomplete-fragment patterns to discard (e.g. "LEY Nº18" without further digits)
FRAGMENT_PATTERNS = [
    re.compile(r"^(LEY|DECRETO|DFL|DS|RESOLUCIÓN)\s*N?[°º]?\s*\d{1,2}$"),
    re.compile(r"^N?[°º]?\s*\d+\s*$"),
]


# === Helpers ===


def is_noise_acronym(token: str) -> bool:
    """Return True if a candidate acronym should be discarded outright."""
    if token in NOISE_TOKENS:
        return True
    if token.isdigit():
        return True
    if len(token) < 2:
        return True
    return False


def is_noise_phrase(phrase: str) -> bool:
    """Return True if a candidate multi-word phrase looks like noise."""
    if not phrase:
        return True
    if any(any(phrase.startswith(bad + " ") or phrase == bad for bad in PHRASE_BAD_FIRST) for _ in [0]):
        return True
    if phrase in NOISE_FULLNAMES:
        return True
    # Drop fragments like "LEY Nº18"
    for pat in FRAGMENT_PATTERNS:
        if pat.match(phrase):
            return True
    # Drop names with too many digits
    if sum(c.isdigit() for c in phrase) > len(phrase) // 3:
        return True
    return False


def first_letters(name: str) -> str:
    """Return the uppercase first-letter sequence of a multi-word name."""
    words = re.split(r"\s+", name)
    return "".join(w[0].upper() for w in words if w and w[0].isupper())


def extract_candidates(articles: list[dict]) -> dict:
    """Return dict of candidates by source, with counts and dispersions."""
    full_text = " ".join(a["texto"] or "" for a in articles)

    # Existing concepts (lower-cased)
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT nombre FROM conceptos")
        existing = {r["nombre"].lower().strip() for r in cur.fetchall()}

    # 1. Acronyms with dispersion (must appear in ≥2 distinct articles)
    acro_per_article = defaultdict(set)
    acro_count = Counter()
    for a in articles:
        for m in ACRONYM_PATTERN.findall(a["texto"] or ""):
            if is_noise_acronym(m):
                continue
            acro_per_article[m].add(a["id"])
            acro_count[m] += 1
    # Filter: appears ≥3 times AND in ≥2 articles AND not in existing
    acronyms = [
        (a, n)
        for a, n in acro_count.most_common()
        if n >= 3 and len(acro_per_article[a]) >= 2 and a.lower() not in existing
    ]

    # 2. Definition phrases
    defs = Counter()
    for pat in DEF_PATTERNS:
        for m in pat.finditer(full_text):
            term = m.group(1).strip()
            term = re.sub(r"\s+", " ", term)
            if 3 < len(term) < 60 and term.lower() not in existing and not is_noise_phrase(term):
                defs[term] += 1

    # 3. Paren-pair (long_name → sigla)
    pairs = []
    seen_pairs = set()
    for m in PAREN_PAIR_PATTERN.finditer(full_text):
        long_name = re.sub(r"\s+", " ", m.group(1).strip())
        sigla = m.group(2)
        # Validate: sigla letters should match start of long_name words
        fl = first_letters(long_name)
        if len(sigla) >= 2 and len(fl) >= len(sigla) // 2:
            if is_noise_phrase(long_name):
                continue
            if is_noise_acronym(sigla):
                continue
            key = (long_name.lower(), sigla)
            if key not in seen_pairs and (long_name.lower() not in existing or sigla.lower() not in existing):
                seen_pairs.add(key)
                pairs.append((long_name, sigla))

    # 4. Multi-word frequent phrases (with dispersion)
    phrase_per_article = defaultdict(set)
    phrase_count = Counter()
    for a in articles:
        for m in PHRASE_PATTERN.findall(a["texto"] or ""):
            phrase = re.sub(r"\s+", " ", m).strip()
            if 6 < len(phrase) < 80 and not is_noise_phrase(phrase):
                phrase_per_article[phrase].add(a["id"])
                phrase_count[phrase] += 1
    phrases = [
        (p, n)
        for p, n in phrase_count.most_common()
        if n >= 10 and len(phrase_per_article[p]) >= 2
        and p.lower() not in existing
        and not any(p.lower().startswith(e) or e.startswith(p.lower()) for e in existing if len(e) > 6)
    ]

    return {
        "acronyms": acronyms,
        "defs": list(defs.items()),
        "pairs": pairs,
        "phrases": phrases[:80],  # cap to top 80 phrases (heavy noise tail)
    }


# === LLM validation ===

VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "is_concept": {"type": "boolean"},
        "category": {
            "type": "string",
            "enum": ["acrónimo", "concepto técnico", "institución", "norma legal", "frase genérica", "fragmento", "nombre propio", "otro"],
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "domain": {
            "type": "string",
            "enum": ["eléctrico", "concursal", "tránsito", "gas", "tarifario", "general", "no-aplica"],
        },
        "reason": {"type": "string"},
    },
    "required": ["is_concept", "category", "confidence", "domain", "reason"],
}


def llm_validate(term: str, context: str = "") -> dict | None:
    """Ask LLM whether `term` is a real concept worth indexing."""
    prompt = f"""Eres experto en normativa eléctrica chilena. Recibís un término candidato extraído de un corpus de leyes/decretos del sector. Tu tarea: decidir si vale la pena registrarlo como concepto en un glosario para RAG.

Término candidato: "{term}"

{f'Contexto donde apareció: "{context[:300]}"' if context else ""}

Responde estrictamente en JSON con:
- is_concept: true/false (¿es un término técnico/legal real, no un fragmento ni un nombre genérico?)
- category: clasificación
- confidence: high|medium|low
- domain: a qué dominio pertenece
- reason: 1 oración explicando

NO inventes definiciones. Solo clasifica."""

    body = {
        "model": MODEL,
        "prompt": prompt,
        "format": VALIDATION_SCHEMA,
        "think": False,
        "stream": False,
        "options": {"num_ctx": 2048, "temperature": 0.0},
    }
    try:
        r = requests.post(OLLAMA_URL, json=body, timeout=60)
        data = r.json()
        return json.loads(data.get("response", "{}"))
    except Exception as e:
        print(f"  LLM error for '{term}': {e}", flush=True)
        return None


# === Main ===


def main():
    print("Loading articles from Postgres...", flush=True)
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, id_norma, numero, texto FROM articulos")
        articles = cur.fetchall()
    print(f"  {len(articles)} articles, {sum(len(a['texto'] or '') for a in articles):,} chars\n", flush=True)

    print("Extracting candidates with improved rules + filters...", flush=True)
    candidates = extract_candidates(articles)
    print(f"  Acronyms      : {len(candidates['acronyms'])}")
    print(f"  Definitions   : {len(candidates['defs'])}")
    print(f"  Paren-pairs   : {len(candidates['pairs'])}")
    print(f"  Multi-phrases : {len(candidates['phrases'])}")
    total = (len(candidates["acronyms"]) + len(candidates["defs"])
             + len(candidates["pairs"]) + len(candidates["phrases"]))
    print(f"  TOTAL         : {total}\n")

    # Build unified candidate list with source tag
    unified = []
    for term, n in candidates["acronyms"]:
        unified.append({"term": term, "source": "acronym", "freq": n})
    for term, n in candidates["defs"]:
        unified.append({"term": term, "source": "definition_pattern", "freq": n})
    for long_name, sigla in candidates["pairs"]:
        unified.append({"term": long_name, "source": "paren_pair", "freq": 1, "sigla": sigla})
    for term, n in candidates["phrases"]:
        unified.append({"term": term, "source": "multi_phrase", "freq": n})

    # Dedupe by term (case-insensitive)
    seen = {}
    for c in unified:
        key = c["term"].lower()
        if key not in seen or c["freq"] > seen[key]["freq"]:
            seen[key] = c
    unified = list(seen.values())
    print(f"After dedupe: {len(unified)} unique candidates")
    print(f"\nValidating each with {MODEL} ...\n")

    results = []
    t0 = time.time()
    for i, cand in enumerate(unified, 1):
        term = cand["term"]
        result = llm_validate(term)
        if result is None:
            cand["validation"] = {"is_concept": None, "error": "llm_failed"}
        else:
            cand["validation"] = result
        results.append(cand)
        # Progress
        if i % 10 == 0 or i == len(unified):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(unified) - i) / rate if rate > 0 else 0
            kept = sum(1 for r in results if r.get("validation", {}).get("is_concept"))
            print(f"  [{i}/{len(unified)}] kept_so_far={kept} elapsed={elapsed:.0f}s rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    # Filter to keep only is_concept=True
    kept = [r for r in results if r.get("validation", {}).get("is_concept")]
    print(f"\nLLM validation done. Kept: {len(kept)} / {len(results)} ({len(kept)/len(results)*100:.1f}%)")

    # Write YAML
    out_path = ROOT / "glossary" / "incoming" / "auto-extracted-clean.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    yaml_obj = {
        "schema_version": 1,
        "generated_at": today,
        "extraction_method": "regex+filters+LLM(qwen3.5:9b)",
        "total_candidates_raw": len(unified),
        "total_kept": len(kept),
        "concepts": [],
    }
    for r in kept:
        v = r["validation"]
        yaml_obj["concepts"].append({
            "id": None,
            "name": r["term"],
            "definition": "",  # deferred — to be filled when added to conceptos table
            "aliases": [{"alias": r["sigla"], "confidence": "high", "validated": False}] if r.get("sigla") else [],
            "source": {
                "norm_id": "extracted_from_corpus",
                "norm_label": f"detected via {r['source']}",
                "article": "varios",
                "url": "",
            },
            "domain_context": v.get("domain", "general"),
            "status": "not_reviewed",
            "relations": {"related": [], "broader": [], "narrower": []},
            "notes": f"freq={r['freq']} category={v.get('category')} reason={v.get('reason', '')[:120]}",
            "extraction_difficulty": f"detected via {r['source']}; LLM confidence={v.get('confidence')}",
            "metadata": {
                "refs_count": r["freq"],
                "last_reviewed_by": "auto+LLM",
                "last_reviewed_date": today,
            },
        })

    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_obj, f, allow_unicode=True, sort_keys=False, width=120)

    print(f"\nWrote {out_path} with {len(kept)} concepts.")
    print(f"\nBreakdown by domain:")
    from collections import Counter as C
    domains = C(c["validation"].get("domain", "?") for c in kept)
    for d, n in domains.most_common():
        print(f"  {d:<20} : {n}")
    print(f"\nBreakdown by confidence:")
    confs = C(c["validation"].get("confidence", "?") for c in kept)
    for c, n in confs.most_common():
        print(f"  {c:<10} : {n}")


if __name__ == "__main__":
    main()
