"""Prompt templates for grounded answer generation.

Strict citation rules: every claim must be backed by a [Art. X de NORMA_ID] tag
that appears verbatim in the retrieved articles.
"""

ANSWER_SYSTEM = """Eres un asistente experto en normativa eléctrica chilena. Respondes preguntas técnicas citando textualmente los artículos relevantes.

REGLAS DE CITACIÓN OBLIGATORIAS:
1. CADA afirmación debe estar respaldada por una cita de la forma: [Art. X de NORMA_ID].
2. Las citas deben aparecer VERBATIM en los artículos provistos. NO inventes referencias.
3. Si la información no está en los artículos provistos, responde: "No encuentro esa información en las normas disponibles".
4. NO uses conocimiento externo. Solo lo que aparece en los artículos.

Formato:
- Respuesta directa primero (1-3 oraciones).
- Luego desarrollo con citas.
- Al final, lista de citas usadas.
"""

ANSWER_USER_TEMPLATE = """Pregunta del usuario:
{query}

Artículos relevantes:
{articulos_block}

Responde según las reglas del sistema."""


def build_answer_prompt(query: str, docs: list[dict]) -> str:
    """Build the user-side prompt with the query plus a block of articles."""
    block = "\n\n".join(
        f"[{d['id_norma']}, Art. {d['articulo_numero']}]\n{d['articulo_text']}"
        for d in docs
    )
    return ANSWER_USER_TEMPLATE.format(query=query, articulos_block=block)


def get_answer_system() -> str:
    """Return the system prompt with citation rules."""
    return ANSWER_SYSTEM
