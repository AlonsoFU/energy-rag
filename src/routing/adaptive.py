"""Adaptive RAG router.

Lightweight TF-IDF + LinearSVC classifier that decides whether a query
should go through the SIMPLE branch (single-norma lookup, definitions,
short factual questions) or the COMPLEJO branch (multi-norma comparisons,
evolution, complex synthesis with query expansion).

Default training data is curated from the Chilean electricity-regulation
domain. Callers may pass their own examples via :meth:`train`.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC


DEFAULT_TRAIN: list[tuple[str, str]] = [
    # Simple
    ("¿qué es COMA?", "simple"),
    ("define potencia firme", "simple"),
    ("Art. 5 del D.S. 62", "simple"),
    ("ley 20.936", "simple"),
    ("LGSE", "simple"),
    ("DFL 4 artículo 102", "simple"),
    ("VATT", "simple"),
    ("¿qué dice el reglamento de transferencias?", "simple"),
    ("definición de servicio público de distribución", "simple"),
    # Complejo
    ("¿cómo se calcula la potencia firme considerando todas las enmiendas?", "complejo"),
    ("compara cómo el D.S. 62 y el DFL 4 regulan la potencia firme", "complejo"),
    ("relación entre el reglamento de transferencias y los servicios complementarios", "complejo"),
    ("evolución del concepto de COMA en la regulación", "complejo"),
    ("qué cambios introduce el D.S. 71 al cálculo de transferencias respecto al D.S. 62 original", "complejo"),
    ("explica el flujo completo de tarificación desde la ley hasta los decretos de fija valores", "complejo"),
    ("interacción entre AVI, VATT y COMA en el cálculo total", "complejo"),
    ("normativa aplicable a generadoras renovables en transmisión troncal", "complejo"),
]


class AdaptiveRouter:
    """Classify queries into 'simple' or 'complejo' branches."""

    def __init__(self):
        self.vec: TfidfVectorizer | None = None
        self.clf: LinearSVC | None = None

    def train(self, examples: list[tuple[str, str]]) -> None:
        X, y = zip(*examples)
        self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        Xt = self.vec.fit_transform(X)
        self.clf = LinearSVC()
        self.clf.fit(Xt, y)

    def train_default(self) -> None:
        self.train(DEFAULT_TRAIN)

    def classify(self, query: str) -> str:
        if not self.clf or not self.vec:
            self.train_default()
        return self.clf.predict(self.vec.transform([query]))[0]
