"""Post-hoc citation repair (CiteFix-similarity variant).

Standard 2025 pattern (CiteFix, ACL 2025 industry; VeriCite, 2025): después de
generar la respuesta, verificar la atribución y CORREGIR las citas en
post-proceso en vez de confiar ciegamente en la auto-cita del LLM.

Cuello que ataca: el gold llega al top-k del retrieval, pero el LLM redacta la
respuesta correcta y CITA el artículo vecino "famoso" en vez del que responde la
pregunta (medido ~7 veces: el retrieval ya no es el límite, la elección de cita
sí). Ej: art 212 (financiamiento del Panel) vs art 208 (qué hace el Panel).

Mecanismo (similarity / cross-encoder, NO NLI puro — no hay modelo NLI offline,
HF_HUB_OFFLINE=1; reusa el `bge-reranker-v2-m3` que ya está cargado en el
pipeline, cabe en la GTX 1080 fp16):

  1. Puntuar relevancia (RESPUESTA ↔ cada doc del pool) con el cross-encoder.
  2. El doc mejor puntuado = el que MEJOR sostiene la respuesta redactada.
  3. Si ese doc NO está citado y su score supera el umbral → AÑADIR su cita.
     Si YA está citado → no tocar (el LLM acertó).

Propiedad de seguridad: SOLO AÑADE citas, nunca borra → cita_ok es MONÓTONA
(no puede regresar por construcción). El costo a vigilar es PRECISIÓN: añadir
una cita de más cuando el top-doc no es el gold ("post-racionalización", el
caveat de 'Correctness is not Faithfulness', SIGIR 2025). Por eso el experimento
mide cita_ok Y precisión de las citas añadidas, no solo el número.

Legal-safe: la cita añadida apunta SIEMPRE a un (id_norma, articulo_numero) real
del pool recuperado (grounding intacto); no inventa fuentes.

Flag-gated (`citation_repair`, default OFF) hasta validar.
"""
from src.pipelines.grounding import extract_citations, _normalize_art


def repair_citations(answer_text: str, docs: list[dict], reranker,
                     max_add: int = 1, min_score: float = 0.0) -> dict:
    """Añade hasta `max_add` citas al artículo que mejor sostiene la respuesta.

    Args:
        answer_text: respuesta ya generada (con sus citas inline).
        docs: pool recuperado (cada uno con id_norma, articulo_numero, contextual_text).
        reranker: cross-encoder con .rerank(query, [docs], top_k) -> [(idx, score)].
            Se le pasa la RESPUESTA como "query" para medir soporte respuesta↔doc.
        max_add: tope de citas a añadir (acota el daño de precisión).
        min_score: umbral de score del cross-encoder para añadir (calibra precisión).

    Returns dict: {text, added (list of "norma/art"), top_score, changed}.
    """
    if not answer_text or not docs or reranker is None:
        return {"text": answer_text, "added": [], "top_score": 0.0, "changed": False}

    # Score RESPUESTA ↔ cada doc. El mejor sostiene mejor lo redactado.
    scored = reranker.rerank(answer_text, [d.get("contextual_text", "") for d in docs],
                             top_k=len(docs))
    if not scored:
        return {"text": answer_text, "added": [], "top_score": 0.0, "changed": False}

    already = {(str(n), _normalize_art(str(a))) for n, a in extract_citations(answer_text)}
    top_score = float(scored[0][1])
    added, suffix = [], []
    for idx, score in scored:
        if len(added) >= max_add:
            break
        d = docs[idx]
        norma = str(d.get("id_norma", ""))
        art = str(d.get("articulo_numero", ""))
        if not norma or not art:
            continue
        key = (norma, _normalize_art(art))
        if key in already:
            # El doc que MEJOR sostiene la respuesta ya está citado → el LLM
            # acertó, no se toca. (Solo rompemos en el tope: si el #1 ya está
            # citado, no buscamos más abajo — añadir el #2 sería ruido.)
            break
        if float(score) < min_score:
            break
        suffix.append(f"[Art. {art} de {norma}]")
        added.append(f"{norma}/{art}")

    if not suffix:
        return {"text": answer_text, "added": [], "top_score": top_score, "changed": False}
    new_text = answer_text.rstrip() + " " + " ".join(suffix)
    return {"text": new_text, "added": added, "top_score": top_score, "changed": True}
