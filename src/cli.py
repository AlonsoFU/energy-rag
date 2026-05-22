import typer
from rich import print as rprint
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(help="Energy-RAG CLI for Chilean electrical regulations")


@app.command()
def ask(
    query: str,
    top_k: int = typer.Option(5, "--top-k", "-k"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    model: str | None = typer.Option(None, "--model"),
    mock: bool = typer.Option(False, "--mock", help="Use mock embedder + reranker (no GPU/downloads)"),
):
    """Ask a question and get a grounded answer with citations."""
    from src.routing.adaptive import AdaptiveRouter
    from src.components.vectorstore import PostgresStore
    from src.components.llm import get_llm_provider
    from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
    from src.pipelines.generate import generate_answer
    from src.core import config as cfg
    from src.storage.connection import with_connection
    import time

    rprint(Panel(f"[bold]Query:[/bold] {query}"))

    # Components — embedder/reranker can be mocked
    if mock:
        class _MockEmbedder:
            def embed(self, texts):
                return [[(hash(t + str(i)) % 1000) / 1000.0 for i in range(1024)] for t in texts]
        class _MockReranker:
            def rerank(self, q, docs, top_k):
                return [(i, 1.0/(i+1)) for i in range(min(len(docs), top_k))]
        embedder = _MockEmbedder()
        reranker = _MockReranker()
    else:
        from src.components.embedder import Qwen3Embedder
        from src.components.reranker import Qwen3Reranker
        embedder = Qwen3Embedder()
        reranker = Qwen3Reranker()

    store = PostgresStore()
    llm = get_llm_provider()
    router = AdaptiveRouter(); router.train_default()

    simple = SimpleRetriever(store, embedder, reranker)
    complejo = ComplexRetriever(store, embedder, reranker, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    t0 = time.time()
    branch, docs = adaptive.retrieve(query, top_k=top_k)
    retrieval_ms = int((time.time() - t0) * 1000)

    rprint(f"[dim]branch: {branch} | retrieval: {retrieval_ms}ms | docs: {len(docs)}[/dim]")

    if verbose:
        for d in docs:
            rprint(f"  • {d['id_norma']} Art. {d['articulo_numero']}  score={d.get('score', 0.0):.3f}")

    chosen_model = model or (cfg.settings.llm_opus if branch == "complejo" else cfg.settings.llm_default)

    if not docs:
        rprint("[yellow]No retrieved docs — skipping generation.[/yellow]")
        return

    t0 = time.time()
    result = generate_answer(query, docs, llm=llm, model=chosen_model)
    gen_ms = int((time.time() - t0) * 1000)

    rprint(Panel(result["text"], title=f"Respuesta ({chosen_model})"))
    if not result["grounding_pass"]:
        rprint("[bold red]⚠️  Grounding NO pasó: citas pueden ser inválidas[/bold red]")

    # Log
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consultas_log (query, branch, n_results, latency_ms,
                                       generation_ms, llm_model, llm_tokens_in,
                                       llm_tokens_out, grounding_pass)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (query, branch, len(docs), retrieval_ms + gen_ms, gen_ms,
             chosen_model, result["tokens_in"], result["tokens_out"],
             result["grounding_pass"]),
        )
        conn.commit()


@app.command()
def ingest(
    skip_contextual: bool = typer.Option(False, "--skip-contextual"),
    mock: bool = typer.Option(False, "--mock"),
    limit: int | None = typer.Option(None, "--limit"),
):
    """Run the full ingest pipeline over all articulos in the DB."""
    from scripts.embed_all import run_embed_all
    run_embed_all(skip_contextual=skip_contextual, mock=mock, limit=limit)


@app.command()
def update(dry_run: bool = typer.Option(False, "--dry-run")):
    """Run the BCN incremental updater (diff + descarga + reindex)."""
    from src.pipelines.update import run_update
    run_update(dry_run=dry_run)


@app.command()
def stats():
    """Show DB and performance stats."""
    from src.storage.connection import with_connection
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM normas"); normas = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM articulos"); articulos = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM fragmentos"); frags = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM referencias"); refs = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM conceptos"); conc = cur.fetchone()[0]
        cur.execute("""
            SELECT branch,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms),
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
                   count(*),
                   avg(grounding_pass::int)
            FROM consultas_log
            WHERE ts > now() - interval '30 days'
            GROUP BY branch
        """)
        perf = cur.fetchall()

    t = Table(title="Energy-RAG stats")
    t.add_column("Métrica"); t.add_column("Valor", justify="right")
    t.add_row("normas", str(normas))
    t.add_row("articulos", str(articulos))
    t.add_row("fragmentos", str(frags))
    t.add_row("referencias", str(refs))
    t.add_row("conceptos", str(conc))
    rprint(t)

    if perf:
        p = Table(title="Performance (30d)")
        for col in ("branch", "p50 (ms)", "p95 (ms)", "count", "grounding %"):
            p.add_column(col)
        for b, p50, p95, n, g in perf:
            p.add_row(b, str(int(p50 or 0)), str(int(p95 or 0)), str(n), f"{(g or 0)*100:.1f}%")
        rprint(p)


@app.command(name="eval")
def eval_cmd(
    eval_file: str = typer.Option("data/eval/queries_chilean_electric.jsonl", "--eval-file"),
    top_k: int = typer.Option(5, "--top-k", "-k"),
    mock: bool = typer.Option(False, "--mock"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip generation entirely (retrieval-only)"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save full results to data/eval/results"),
    json_out: bool = typer.Option(False, "--json", help="Print full metrics dict as JSON"),
):
    """Run evaluation against a JSONL eval set (recall@5 + grounding + latency)."""
    import json as _json
    from src.eval.deepeval_runner import run_deepeval, render_summary
    from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
    from src.routing.adaptive import AdaptiveRouter
    from src.components.vectorstore import PostgresStore
    from src.components.llm import get_llm_provider

    if mock:
        class _ME:
            def embed(self, texts): return [[(hash(t + str(i)) % 1000)/1000.0 for i in range(1024)] for t in texts]
        class _MR:
            def rerank(self, q, docs, top_k): return [(i, 1.0/(i+1)) for i in range(min(len(docs), top_k))]
        e, r = _ME(), _MR()
    else:
        from src.components.embedder import Qwen3Embedder
        from src.components.reranker import Qwen3Reranker
        e, r = Qwen3Embedder(), Qwen3Reranker()

    from src.core import config as cfg
    pool = cfg.settings.retrieval_pool_depth

    store = PostgresStore()
    llm = get_llm_provider()
    router = AdaptiveRouter(); router.train_default()
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool)
    complejo = ComplexRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    def _progress(i: int, n: int, row: dict) -> None:
        marker = "+" if row["retrieval_hit"] else ("~" if row["retrieval_norma_only_hit"] else ".")
        # Use parens around the branch name — rich treats `[...]` as markup.
        rprint(f"[dim]({i}/{n}) {marker} {row['latency_ms']}ms ({row['branch']}) {row['query'][:60]}[/dim]")

    metrics = run_deepeval(
        eval_file=eval_file,
        retriever=adaptive,
        top_k=top_k,
        llm=None if no_llm else llm,
        save_results=save,
        progress=_progress,
    )

    render_summary(metrics)
    if "results_path" in metrics:
        rprint(f"[green]Saved full results to {metrics['results_path']}[/green]")
    if json_out:
        rprint(_json.dumps({k: v for k, v in metrics.items() if k != "per_query"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
