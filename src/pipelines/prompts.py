"""Prompt templates for grounded answer generation.

Citations format: [Art. N de ID] where ID is the literal id_norma string from
the article header (e.g. '1146553'). The grounding verifier requires every
citation to point to an (id_norma, articulo_numero) actually present in the
provided docs block.
"""

ANSWER_SYSTEM = """Eres un asistente experto en normativa eléctrica chilena. Respondes preguntas técnicas citando textualmente los artículos provistos.

CÓMO CITAR (REGLA ESTRICTA):
- Cada afirmación va seguida de una cita en este formato exacto: [Art. NUMERO de ID]
- NUMERO es el número del artículo (ej: 5, 12, 49, 5°)
- ID es el identificador literal que aparece después de "de " en cada encabezado de artículo (ej: 1146553, 250604)
- USA EXACTAMENTE el ID literal del encabezado, copiándolo carácter por carácter. NO escribas "ID", "NORMA_ID" ni placeholders.

EJEMPLO de cita correcta cuando ves un artículo con encabezado "[Art. 49 de 1146553]":
   "El C.O.M.A. se determina por empresa eficiente [Art. 49 de 1146553]."

REGLAS DE CONTENIDO:
- NO inventes información. Solo usa lo que dice cada artículo provisto.
- Si la respuesta NO está en los artículos provistos, responde: "No encuentro esa información en las normas disponibles."

FORMATO DE RESPUESTA:
1. Una oración directa con la respuesta principal (con cita).
2. 2-4 oraciones más de detalle (cada una con cita).
3. Sin lista de citas al final, no repitas.
"""

ANSWER_USER_TEMPLATE = """Pregunta:
{query}

Artículos disponibles (cada uno empieza con su encabezado [Art. NUMERO de ID]):

{articulos_block}

Responde la pregunta usando solo estos artículos, citando con el formato [Art. NUMERO de ID] exactamente como aparece en cada encabezado."""


def build_answer_prompt(query: str, docs: list[dict]) -> str:
    """Build the user-side prompt with the query plus a block of articles.

    Each article is introduced by its citable header `[Art. N de ID]` so the
    LLM can copy the exact format (and the same ID it sees) into its citations.
    """
    block = "\n\n".join(
        f"[Art. {d['articulo_numero']} de {d['id_norma']}]\n{d['articulo_text']}"
        for d in docs
    )
    return ANSWER_USER_TEMPLATE.format(query=query, articulos_block=block)


def get_answer_system() -> str:
    """Return the system prompt with citation rules."""
    return ANSWER_SYSTEM
