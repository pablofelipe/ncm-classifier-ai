import json
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from eval.schema import CaseResult, EvalReport, EvalSuite
from src.api.dependencies import build_classify_use_case
from src.config import settings
from src.core.domain.ncm import ClassificationResult, ProductQuery
from src.core.use_cases.classify_product import ClassifyProduct

_MODES = ("direct", "colloquial", "poverty", "negation", "frontier", "multi_attr")


def load_eval_suite(path: str | Path) -> EvalSuite:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvalSuite.model_validate(data)


@dataclass(frozen=True)
class CrossValidationReport:
    """Result of cross-checking eval cases against the indexed TIPI NCMs.

    The in-scope rule is keyed on ``suite.corpus_chapters`` (the chapters the
    loaded corpus actually covers): a case is *in-scope* when its
    ``answer_chapter`` is one of them. ``in_scope_missing`` (an in-scope NCM
    absent from the corpus) is the only hard failure ``ok`` reflects.
    ``out_of_scope_warned`` lists out-of-scope cases absent from the corpus —
    informational only, never a failure.

    This one rule reproduces both historical behaviours: for v1
    (``corpus_chapters=[22]``) a case answering in Ch.20 is out-of-scope and
    only warned; for v2 (``[20, 21, 22]``) every case is in-scope, so any
    missing NCM is a hard failure.

    A prefix mismatch (``expected_ncm`` not starting with ``answer_chapter``)
    is an invariant violation and is raised, not collected here.
    """

    total: int
    in_scope: int
    in_scope_present: int
    in_scope_missing: list[str] = field(default_factory=list)
    out_of_scope: int = 0
    out_of_scope_warned: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.in_scope_missing


def cross_validate_against_tipi(suite: EvalSuite, corpus_ncms: set[str]) -> CrossValidationReport:
    corpus_chapters = set(suite.corpus_chapters)
    in_scope = 0
    in_scope_present = 0
    in_scope_missing: list[str] = []
    out_of_scope = 0
    out_of_scope_warned: list[str] = []

    for case in suite.cases:
        # Hard invariant, checked for every case regardless of scope: the NCM
        # must belong to the chapter the case declares as the answer.
        if int(case.expected_ncm[:2]) != case.answer_chapter:
            raise ValueError(
                f"case {case.id}: expected_ncm {case.expected_ncm!r} does not "
                f"start with answer_chapter {case.answer_chapter}"
            )

        if case.answer_chapter in corpus_chapters:
            in_scope += 1
            if case.expected_ncm in corpus_ncms:
                in_scope_present += 1
            else:
                in_scope_missing.append(case.id)
        else:
            out_of_scope += 1
            if case.expected_ncm not in corpus_ncms:
                out_of_scope_warned.append(case.id)

    return CrossValidationReport(
        total=len(suite.cases),
        in_scope=in_scope,
        in_scope_present=in_scope_present,
        in_scope_missing=in_scope_missing,
        out_of_scope=out_of_scope,
        out_of_scope_warned=out_of_scope_warned,
    )


def classify_via_use_case(query: ProductQuery, use_case: ClassifyProduct) -> ClassificationResult:
    """Thin wrapper over use_case.execute.

    Isolates the call site so future tests can mock the classification step,
    and so the measurement layer never reaches past the use case into adapters.
    """
    return use_case.execute(query)


def evaluate_suite(suite: EvalSuite, use_case: ClassifyProduct) -> EvalReport:
    """Run every case through the use case and aggregate top-1/top-3 accuracy.

    ``case.query`` maps to ``product_name`` and ``case.product_description`` to
    ``description`` (rich in v1, empty in v2). The text is identical to what v1
    sent before the schema unification — only the field was renamed.
    """
    per_case: list[CaseResult] = []
    top_1_hits = 0
    top_3_hits = 0

    for case in suite.cases:
        query = ProductQuery(product_name=case.query, description=case.product_description)
        result = classify_via_use_case(query, use_case)
        predicted = [c.ncm_code for c in result.top_candidates]

        top_1 = predicted[0] == case.expected_ncm
        top_3 = case.expected_ncm in predicted
        top_1_hits += int(top_1)
        top_3_hits += int(top_3)

        per_case.append(
            CaseResult(
                case_id=case.id,
                expected_ncm=case.expected_ncm,
                predicted_ncms=predicted,
                top_1_hit=top_1,
                top_3_hit=top_3,
            )
        )

    return EvalReport(
        total=len(suite.cases),
        top_1_hits=top_1_hits,
        top_3_hits=top_3_hits,
        per_case=per_case,
    )


def _find_latest_tipi_json(tipi_dir: str | Path, chapter: str) -> Path:
    files = sorted(Path(tipi_dir).glob(f"tipi_{chapter}_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No tipi_{chapter}_*.json found in {tipi_dir}. Run: python scripts/ingest_tipi.py"
        )
    return files[0]


def _find_beverage_corpus(tipi_dir: str | Path) -> Path:
    """Locate the multi-chapter beverage corpus.

    It spans Chapters 20/21/22 in one file, so it cannot follow the per-chapter
    ``tipi_{chapter}_*.json`` convention; it uses the fixed ``tipi_beverage_*``
    prefix and is referenced directly.
    """
    files = sorted(Path(tipi_dir).glob("tipi_beverage_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(f"No tipi_beverage_*.json found in {tipi_dir}. Run: make index-v2")
    return files[0]


def _resolve_corpus_path(suite: EvalSuite, tipi_dir: str | Path) -> Path:
    """Pick the TIPI corpus by the suite's ``corpus_chapters``.

    A single chapter → the per-chapter file (v1, e.g. Ch.22 → tipi_22_*.json);
    multiple chapters → the multi-chapter beverage corpus (v2).
    """
    chapters = sorted(set(suite.corpus_chapters))
    if len(chapters) == 1:
        return _find_latest_tipi_json(tipi_dir, str(chapters[0]))
    return _find_beverage_corpus(tipi_dir)


def _load_tipi(path: Path) -> tuple[list[dict[str, object]], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, object]] = payload["entries"]
    return entries, payload.get("tipi_version", path.name)


def main(
    eval_path: str | Path = "eval/v1_cases.json",
    tipi_dir: str | Path = "data/tipi",
    use_case_factory: Callable[[], ClassifyProduct] = build_classify_use_case,
) -> int:
    suite = load_eval_suite(eval_path)
    _print_stats(suite)

    corpus_path = _resolve_corpus_path(suite, tipi_dir)
    entries, tipi_version = _load_tipi(corpus_path)
    corpus_ncms = {str(entry["ncm"]) for entry in entries}

    report = cross_validate_against_tipi(suite, corpus_ncms)
    _print_report(suite, report, tipi_version)

    # Measurement layer: run the use case (default: real Chroma + e5-small,
    # ADR-0004; injectable so unit tests need no index) over the suite and
    # report accuracy. Never gates the exit code; the CI gate stays governed
    # solely by cross-validation.
    use_case = use_case_factory()
    eval_report = evaluate_suite(suite, use_case)
    _print_evaluation(suite, eval_report)

    return 0 if report.ok else 1


def _print_stats(suite: EvalSuite) -> None:
    chapters = ", ".join(str(c) for c in suite.corpus_chapters)
    print(f"Suite:         {suite.version}")
    print(f"Corpus chaps:  {chapters}")
    print(f"Total cases:   {len(suite.cases)}")

    if not suite.cases:
        print("\n(no cases yet)")
        return

    diff = Counter(c.difficulty for c in suite.cases)
    print("\nBy difficulty:")
    for level in ("easy", "medium", "hard"):
        print(f"  {level:<8} {diff.get(level, 0)}")

    mode = Counter(c.mode for c in suite.cases)
    print("\nBy mode:")
    for label in _MODES:
        print(f"  {label:<12} {mode.get(label, 0)}")


def _print_report(suite: EvalSuite, report: CrossValidationReport, tipi_version: str) -> None:
    ncm_by_id = {c.id: c.expected_ncm for c in suite.cases}
    warned = f" ({', '.join(report.out_of_scope_warned)})" if report.out_of_scope_warned else ""

    print(f"\nCross-validation: corpus {tipi_version}")
    print(f"In-scope:     {report.in_scope_present}/{report.in_scope} present")
    print(f"Out-of-scope: {len(report.out_of_scope_warned)} warned{warned}")

    if report.ok:
        print("Status: OK ✓")
    else:
        print("Status: FAIL ✗")
        missing = ", ".join(f"{cid} ({ncm_by_id.get(cid, '?')})" for cid in report.in_scope_missing)
        print(f"Missing: {missing}")


def _print_evaluation(suite: EvalSuite, report: EvalReport) -> None:
    print(
        f"\nEvaluation: semantic retrieval (Chroma embedder={settings.embedder.value} "
        f"enrich={settings.enrich_strategy.value} + Passthrough rerank)"
    )
    print(f"Top-1 accuracy:  {report.top_1_hits}/{report.total} = {report.top_1_accuracy:.1%}")
    print(f"Top-3 accuracy:  {report.top_3_hits}/{report.total} = {report.top_3_accuracy:.1%}")
    print("ECE:             informative only (1 - cosine distance is not calibrated)")

    difficulty_by_id = {c.id: c.difficulty for c in suite.cases}
    print("\nPer-difficulty breakdown:")
    for level in ("easy", "medium", "hard"):
        cases = [r for r in report.per_case if difficulty_by_id.get(r.case_id) == level]
        _print_breakdown_row(level, cases)

    mode_by_id = {c.id: c.mode for c in suite.cases}
    print("\nPer-mode breakdown:")
    for label in _MODES:
        cases = [r for r in report.per_case if mode_by_id.get(r.case_id) == label]
        _print_breakdown_row(label, cases)


def _print_breakdown_row(label: str, cases: list[CaseResult]) -> None:
    n = len(cases)
    t1 = sum(r.top_1_hit for r in cases)
    t3 = sum(r.top_3_hit for r in cases)
    print(f"  {label + ':':<12} {t1}/{n} top-1, {t3}/{n} top-3")


if __name__ == "__main__":
    # Ensure ✓/✗ render on legacy consoles (e.g. Windows cp1252) instead of
    # crashing with UnicodeEncodeError — which would corrupt the exit code.
    sys.stdout.reconfigure(encoding="utf-8")
    eval_path = sys.argv[1] if len(sys.argv) > 1 else "eval/v1_cases.json"
    sys.exit(main(eval_path=eval_path))
