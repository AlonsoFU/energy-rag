"""Extensive empirical study of how concepts/aliases/derogations are written
across the WHOLE corpus, to ground the extraction-pipeline design.

Quantifies each candidate pattern (counts + examples + edge cases) so the
extractor is built on evidence, not on a few hand-picked samples.

Read-only. No Ollama. Run: python -m scripts.study_extraction_patterns
"""
import re
import psycopg
from collections import Counter
from src.core import config


def fetch_all():
    with psycopg.connect(config.settings.dsn()) as c, c.cursor() as cur:
        cur.execute("SELECT id_norma, numero, texto FROM articulos")
        return cur.fetchall()


def hr(title):
    print(f"\n{'═'*70}\n{title}\n{'═'*70}")


def main():
    rows = fetch_all()
    print(f"corpus: {len(rows)} artículos")

    # ── 1. DEFINITION ARTICLES ─────────────────────────────────────────
    hr("1. ARTÍCULOS DE DEFINICIONES — detección y formato")
    def_openers = [
        ("se entenderá por", re.compile(r"se entender[áa]\s+por", re.I)),
        ("para los efectos", re.compile(r"para los efectos", re.I)),
        ("se define como", re.compile(r"se define como", re.I)),
        ("definiciones (título)", re.compile(r"\bdefiniciones\b", re.I)),
    ]
    glossary_arts = []
    for op_name, rx in def_openers:
        hits = [(n, num) for n, num, t in rows if t and rx.search(t)]
        print(f"  '{op_name}': {len(hits)} artículos")
    # Articles that look like real glossaries (have lettered/numbered item list)
    item_rx = re.compile(r"(?:^|\n)\s*(?:[a-zñ]{1,2}|\d{1,2})[.)]\s+[A-ZÁÉÍÓÚ]")
    for n, num, t in rows:
        if t and re.search(r"se entender[áa]\s+por", t, re.I) and len(item_rx.findall(t)) >= 3:
            glossary_arts.append((n, num, t))
    normas_with_gloss = sorted({n for n, _, _ in glossary_arts})
    print(f"  → glosarios reales (>=3 ítems lista): {len(glossary_arts)} arts en {len(normas_with_gloss)} normas")

    # ── 2. ACRONYM : EXPANSION pairs inside glossaries ─────────────────
    hr("2. PARES SIGLA:EXPANSIÓN dentro de glosarios")
    # item shape: "letra. TERM: definición;"  capture TERM and first chunk of def
    item_pair = re.compile(
        r"(?:^|\n)\s*(?:[a-zñ]{1,2}|\d{1,2})[.)]\s+([^:\n]{2,70}?):\s*([^;\n]{3,120})",
    )
    acronym_term = re.compile(r"^(?:[A-ZÑ]\.){2,}[A-ZÑ]?\.?$|^[A-ZÑ]{2,8}$")
    pairs, acro_pairs, shortname_pairs = [], [], []
    for n, num, t in glossary_arts:
        for term, defn in item_pair.findall(t):
            term = term.strip()
            defn = defn.strip()
            pairs.append((n, term, defn))
            if acronym_term.match(term.replace(" ", "")):
                acro_pairs.append((n, term, defn))
            # short-name: term is a single capitalized word AND appears as the
            # first word(s) of its own definition (e.g. Comisión: Comisión Nac…)
            elif term and defn.lower().startswith(term.lower().rstrip("s")):
                shortname_pairs.append((n, term, defn))
    print(f"  total ítems término:definición parseados: {len(pairs)}")
    print(f"  → SIGLA:expansión (term acrónimo): {len(acro_pairs)}")
    for n, term, defn in acro_pairs[:8]:
        print(f"      [{n}] {term!r} → {defn[:55]!r}")
    print(f"  → forma-corta (term ⊂ inicio def): {len(shortname_pairs)}")
    for n, term, defn in shortname_pairs[:6]:
        print(f"      [{n}] {term!r} → {defn[:55]!r}")

    # ── 3. "en adelante" alias declarations in body ────────────────────
    hr("3. PATRÓN 'en adelante' — alias vs temporal")
    en_adel = re.compile(
        r"en adelante,?\s*(?:e\s+indistintamente,?\s*)?(?:la|el|los|las)?\s*[«\"]?([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\.\s]{1,40}?)[»\"]?(?=[\s,\.;\)])",
    )
    temporal_rx = re.compile(r"\d{4}\s+en adelante|en adelante\s*[\.\"]")
    alias_hits, temporal_hits = [], 0
    for n, num, t in rows:
        if not t or "en adelante" not in t.lower():
            continue
        for m in re.finditer(r"en adelante", t, re.I):
            window = t[m.start():m.start()+60]
            if temporal_rx.search(window):
                temporal_hits += 1
                continue
            am = en_adel.search(t[m.start():m.start()+80])
            if am:
                alias_hits.append((n, am.group(1).strip()))
    print(f"  ocurrencias 'en adelante' clasificadas como ALIAS: {len(alias_hits)}")
    print(f"  ocurrencias temporales (falso positivo, filtradas): {temporal_hits}")
    for n, a in alias_hits[:12]:
        print(f"      [{n}] → {a!r}")

    # ── 4. parenthetical (SIGLA) ───────────────────────────────────────
    hr("4. PATRÓN 'Nombre (SIGLA)'")
    paren = re.compile(r"([A-ZÁÉÍÓÚ][\wÁÉÍÓÚáéíóúñ]+(?:\s+[\wÁÉÍÓÚáéíóúñ]+){0,6})\s*\(\s*([A-ZÑ]{2,8})\s*\)")
    paren_hits = []
    for n, num, t in rows:
        if not t:
            continue
        for m in paren.finditer(t):
            paren_hits.append((n, m.group(1).strip(), m.group(2)))
    print(f"  total 'Nombre (SIGLA)': {len(paren_hits)}")
    for n, name, sig in paren_hits[:10]:
        print(f"      [{n}] {sig} ← {name[:50]!r}")

    # ── 5. derogations / modifications ─────────────────────────────────
    hr("5. DEROGACIONES / MODIFICACIONES")
    deroga_verbs = re.compile(r"\b(der[óo]gan?se|mod[ií]f[íi]case|reempl[áa]zase|interc[áa]lase|sustit[úu]yese|agr[ée]gase)\b", re.I)
    ref_norma = re.compile(r"(?:ley|decreto|D\.?F\.?L\.?|reglamento)\s+(?:con fuerza de ley\s+)?N[°º]\s*([\d\.]+)", re.I)
    verb_counter = Counter()
    deroga_with_ref, deroga_total = 0, 0
    examples = []
    for n, num, t in rows:
        if not t:
            continue
        for vm in deroga_verbs.finditer(t):
            deroga_total += 1
            verb_counter[vm.group(1).lower()] += 1
            window = t[vm.start():vm.start()+120]
            rm = ref_norma.search(window)
            if rm:
                deroga_with_ref += 1
                if len(examples) < 10:
                    examples.append((n, vm.group(1), rm.group(1)))
    print(f"  total verbos de derogación/modif: {deroga_total}")
    print(f"  por verbo: {dict(verb_counter)}")
    print(f"  con referencia a norma resoluble (N° X): {deroga_with_ref}")
    for n, verb, ref in examples:
        print(f"      [{n}] {verb} → ley/decreto N° {ref}")

    # ── 6. resolvability of references to our id_norma ─────────────────
    hr("6. ¿Podemos resolver 'ley N° X' a nuestro id_norma?")
    with psycopg.connect(config.settings.dsn()) as c, c.cursor() as cur:
        cur.execute("SELECT tipo, numero, count(*) FROM normas GROUP BY tipo, numero ORDER BY 1,2 LIMIT 20")
        print("  muestra de (tipo, numero) en normas:")
        for tipo, numero, cnt in cur.fetchall():
            print(f"      {tipo} {numero}")

    # ── 7. coverage gap: concepts that COULD get aliases ───────────────
    hr("7. BRECHA DE COBERTURA")
    with psycopg.connect(config.settings.dsn()) as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM conceptos")
        total_c = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM conceptos WHERE aliases IS NOT NULL AND array_length(aliases,1)>0")
        with_alias = cur.fetchone()[0]
    print(f"  conceptos: {total_c}, con aliases: {with_alias} ({with_alias/total_c*100:.0f}%)")
    print(f"  pares SIGLA:expansión detectados en glosarios: {len(acro_pairs)}")
    print(f"  → muchos de esos {len(acro_pairs)} acrónimos podrían ser aliases que hoy faltan")


if __name__ == "__main__":
    main()
