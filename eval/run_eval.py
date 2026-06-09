import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from eval.schema import EvalSuite


def load_eval_suite(path: str | Path) -> EvalSuite:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvalSuite.model_validate(data)


@dataclass(frozen=True)
class CrossValidationReport:
    """Result of cross-checking eval cases against the indexed TIPI NCMs.

    A case is *in-scope* when ``answer_chapter == suite.chapter_scope`` — the
    correct answer lives in the chapter the classifier covers. ``in_scope_missing``
    (an in-scope NCM absent from the TIPI index) is the only hard failure that
    ``ok`` reflects. ``out_of_scope_warned`` lists out-of-scope cases absent from
    the index — informational only, never a failure.

    A prefix mismatch (``expected_ncm`` not starting with ``answer_chapter``) is
    an invariant violation and is raised, not collected here.
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


def cross_validate_against_tipi(
    suite: EvalSuite, tipi_ncms: set[str]
) -> CrossValidationReport:
    in_scope = 0
    in_scope_present = 0
    in_scope_missing: list[str] = []
    out_of_scope = 0
    out_of_scope_warned: list[str] = []

    for case in suite.cases:
        # Hard invariant, checked for every case regardless of scope: the NCM
        # must belong to the chapter the case declares as the answer.
        if case.expected_ncm[:2] != case.answer_chapter:
            raise ValueError(
                f"case {case.id}: expected_ncm {case.expected_ncm!r} does not "
                f"start with answer_chapter {case.answer_chapter!r}"
            )

        if case.answer_chapter == suite.chapter_scope:
            in_scope += 1
            if case.expected_ncm in tipi_ncms:
                in_scope_present += 1
            else:
                in_scope_missing.append(case.id)
        else:
            out_of_scope += 1
            if case.expected_ncm not in tipi_ncms:
                out_of_scope_warned.append(case.id)

    return CrossValidationReport(
        total=len(suite.cases),
        in_scope=in_scope,
        in_scope_present=in_scope_present,
        in_scope_missing=in_scope_missing,
        out_of_scope=out_of_scope,
        out_of_scope_warned=out_of_scope_warned,
    )


def _find_latest_tipi_json(tipi_dir: str | Path, chapter: str) -> Path:
    files = sorted(Path(tipi_dir).glob(f"tipi_{chapter}_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No tipi_{chapter}_*.json found in {tipi_dir}. "
            "Run: python scripts/ingest_tipi.py"
        )
    return files[0]


def _load_tipi(path: Path) -> tuple[set[str], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ncms = {entry["ncm"] for entry in payload["entries"]}
    return ncms, payload.get("tipi_version", path.name)


def _print_report(
    suite: EvalSuite, report: CrossValidationReport, tipi_version: str
) -> None:
    ncm_by_id = {c.id: c.expected_ncm for c in suite.cases}

    warned = (
        f" ({', '.join(report.out_of_scope_warned)})"
        if report.out_of_scope_warned
        else ""
    )

    print(f"\nCross-validation: TIPI {tipi_version}")
    print(f"In-scope:     {report.in_scope_present}/{report.in_scope} present")
    print(f"Out-of-scope: {len(report.out_of_scope_warned)} warned{warned}")

    if report.ok:
        print("Status: OK ✓")
    else:
        print("Status: FAIL ✗")
        missing = ", ".join(
            f"{cid} ({ncm_by_id.get(cid, '?')})" for cid in report.in_scope_missing
        )
        print(f"Missing: {missing}")


def main(
    eval_path: str | Path = "eval/v1_cases.json",
    tipi_dir: str | Path = "data/tipi",
) -> int:
    suite = load_eval_suite(eval_path)
    _print_stats(suite)

    tipi_json = _find_latest_tipi_json(tipi_dir, suite.chapter_scope)
    tipi_ncms, tipi_version = _load_tipi(tipi_json)

    report = cross_validate_against_tipi(suite, tipi_ncms)
    _print_report(suite, report, tipi_version)

    return 0 if report.ok else 1


def _print_stats(suite: EvalSuite) -> None:
    print(f"Suite:         {suite.version}")
    print(f"TIPI version:  {suite.tipi_version}")
    print(f"Chapter scope: {suite.chapter_scope}")
    print(f"Total cases:   {len(suite.cases)}")

    if not suite.cases:
        print("\n(no cases yet)")
        return

    diff = Counter(c.difficulty for c in suite.cases)
    src = Counter(c.source for c in suite.cases)

    print("\nBy difficulty:")
    for level in ("easy", "medium", "hard"):
        print(f"  {level:<8} {diff.get(level, 0)}")

    print("\nBy source:")
    for label in sorted(src):
        print(f"  {label:<12} {src[label]}")


if __name__ == "__main__":
    # Ensure ✓/✗ render on legacy consoles (e.g. Windows cp1252) instead of
    # crashing with UnicodeEncodeError — which would corrupt the exit code.
    sys.stdout.reconfigure(encoding="utf-8")
    eval_path = sys.argv[1] if len(sys.argv) > 1 else "eval/v1_cases.json"
    sys.exit(main(eval_path=eval_path))
