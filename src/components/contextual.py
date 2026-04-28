from src.components.llm import LLMProvider, get_llm_provider

CONTEXTUAL_PROMPT = """Eres un experto en normativa eléctrica chilena. Vas a recibir un fragmento de un artículo legal junto con el contexto del artículo padre.

Tu tarea: en 50-100 tokens, escribe contexto que ubique este fragmento dentro de la norma y artículo, mencionando los temas principales que regula.

NO repitas el fragmento. NO uses prefijos como "Este fragmento". Devuelve solo el texto del contexto.

Norma: {norma_titulo}
Artículo: {articulo_numero}

FRAGMENTO:
{fragment_text}"""


class ContextualEnricher:
    def __init__(self, llm: LLMProvider | None = None, model: str | None = None):
        self.llm = llm or get_llm_provider()
        # Lazy resolve model from current settings (so tests with monkeypatched env work)
        from src.core import config as cfg
        self.model = model or cfg.settings.llm_haiku

    def enrich(self, norma_titulo: str, articulo_numero: str, fragment_text: str) -> str:
        prompt = CONTEXTUAL_PROMPT.format(
            norma_titulo=norma_titulo,
            articulo_numero=articulo_numero,
            fragment_text=fragment_text,
        )
        resp = self.llm.generate(prompt, model=self.model, max_tokens=150, cache_control=False)
        return f"{resp.text.strip()}\n\n{fragment_text}"
