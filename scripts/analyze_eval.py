"""ANALYSIS SCRIPT (diagnostic, not imported by src/).

Runs every eval case through the real retrieval (k=10) and dumps per-case
predictions with scores, plus a 10-bin ECE over the top-1 score. The k=10
depth (vs the pipeline's top-3) is diagnostic only: it shows where the
correct NCM ranks when it misses the top-3.

Reused across ADRs that need a per-case retrieval snapshot: it backs both
docs/adr/assets/0004-analysis.json and docs/adr/assets/0005-analysis.json
(stdout redirected). The enrich strategy is read from settings, so it
reports against whichever index is currently built. Requires a built
index: make index (or ENRICH_DOCUMENTS=1 make index for the enriched run).
"""

import json
import sys

from eval.run_eval import load_eval_suite
from src.config import settings
from src.core.domain.ncm import ProductQuery
from src.retrieval.chroma_client import get_collection
from src.retrieval.embedding import make_embedding_function
from src.retrieval.hierarchical import ChromaRetrievalAdapter


def main() -> None:
    suite = load_eval_suite("eval/v1_cases.json")
    adapter = ChromaRetrievalAdapter(
        get_collection(),
        make_embedding_function(settings.embedder),
        expected_strategy=settings.enrich_strategy,
        expected_embedder=settings.embedder,
    )

    rows = []
    for case in suite.cases:
        query = ProductQuery(product_name=case.product_name, description=case.product_description)
        candidates = adapter.retrieve_candidates(query, k=10)
        preds = [{"ncm": c.ncm_code, "score": round(c.score, 4)} for c in candidates]
        ranked = [p["ncm"] for p in preds]
        rank = ranked.index(case.expected_ncm) + 1 if case.expected_ncm in ranked else None
        rows.append(
            {
                "id": case.id,
                "product_name": case.product_name,
                "expected": case.expected_ncm,
                "difficulty": case.difficulty,
                "confusion_chapters": case.confusion_chapters,
                "top1_hit": ranked[0] == case.expected_ncm,
                "top3_hit": case.expected_ncm in ranked[:3],
                "rank_in_top10": rank,
                "top1_score": preds[0]["score"],
                "top3": preds[:3],
            }
        )

    n_bins = 10
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for r in rows:
        b = min(int(r["top1_score"] * n_bins), n_bins - 1)
        bins[b].append((r["top1_score"], r["top1_hit"]))
    n = len(rows)
    ece = 0.0
    bin_table = []
    for i, b in enumerate(bins):
        if not b:
            continue
        conf = sum(s for s, _ in b) / len(b)
        acc = sum(h for _, h in b) / len(b)
        ece += (len(b) / n) * abs(acc - conf)
        bin_table.append(
            {
                "bin": f"[{i / 10:.1f},{(i + 1) / 10:.1f})",
                "n": len(b),
                "mean_conf": round(conf, 4),
                "acc": round(acc, 4),
            }
        )

    json.dump(
        {"cases": rows, "ece_top1_10bins": round(ece, 4), "ece_bins": bin_table},
        sys.stdout,
        indent=1,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
