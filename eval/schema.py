from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

# Failure-mode taxonomy (ADR-0009). Required on every case in both suites.
Mode = Literal["direct", "colloquial", "poverty", "negation", "frontier", "multi_attr"]


class EvalCase(BaseModel):
    """A single labelled eval case — unified schema for both v1 and v2.

    v1 and v2 share an identical field set (only the corpus they run against
    differs, detected on the suite via ``corpus_chapters``). v1 carries the
    rich text fields (``product_description``, ``rationale``, ``source``); v2
    leaves them empty. None is ever fabricated — empty is empty.
    """

    # ``case-001`` (v1) or ``c001`` (v2).
    id: str = Field(pattern=r"^(?:case-\d{3}|c\d{3})$")
    # The text sent to the classifier (v1's ``product_name`` was renamed here).
    query: str = Field(min_length=1, max_length=300)
    # Rich in v1; empty in v2 (never fabricated).
    product_description: str = Field(default="", max_length=300)
    expected_ncm: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    difficulty: Literal["easy", "medium", "hard"]
    mode: Mode
    # TIPI chapter where the correct answer actually lives (first 2 digits of
    # expected_ncm); a hard invariant (validated below).
    answer_chapter: int
    # Chapter the query superficially evokes (informational). In v1 this equals
    # answer_chapter; in v2 a frontier query may evoke a different chapter.
    chapter: int
    # Chapters where the product could be wrongly classified. Informational,
    # for error analysis. Never contains answer_chapter.
    confusion_chapters: list[int] = Field(default_factory=list)
    # Rich in v1; empty in v2 (never fabricated).
    rationale: str = ""
    # Rich in v1 (ecommerce/label/invoice/synthetic); empty in v2.
    source: str = ""

    @model_validator(mode="after")
    def _answer_chapter_matches_ncm(self) -> "EvalCase":
        if self.answer_chapter != int(self.expected_ncm[:2]):
            raise ValueError(
                f"answer_chapter {self.answer_chapter} must match the first "
                f"two digits of expected_ncm {self.expected_ncm!r}"
            )
        return self

    @model_validator(mode="after")
    def _confusion_excludes_answer(self) -> "EvalCase":
        if self.answer_chapter in self.confusion_chapters:
            raise ValueError(
                f"confusion_chapters must not contain answer_chapter {self.answer_chapter}"
            )
        return self

    @model_validator(mode="after")
    def _confusion_chapters_unique(self) -> "EvalCase":
        if len(self.confusion_chapters) != len(set(self.confusion_chapters)):
            raise ValueError("confusion_chapters must not contain duplicates")
        return self


class EvalSuite(BaseModel):
    """A labelled eval suite — unified schema for both v1 and v2.

    ``corpus_chapters`` both documents the suite's scope and drives which TIPI
    corpus run_eval loads ([22] → per-chapter Ch.22 file; [20, 21, 22] → the
    multi-chapter beverage corpus). The schema itself is single.
    """

    version: str
    description: str = ""
    corpus_chapters: list[int] = Field(default_factory=list)
    cases: list[EvalCase]

    @model_validator(mode="after")
    def _unique_ids(self) -> "EvalSuite":
        ids = [c.id for c in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs must be unique")
        return self


# ---------------------------------------------------------------------------
# Eval results — produced by evaluate_suite, not loaded from disk
# ---------------------------------------------------------------------------


class CaseResult(BaseModel):
    """Outcome of running one EvalCase through the classifier.

    ``predicted_ncms`` holds exactly 3 candidates (top-3 of the v1 pipeline),
    in rank order. ``top_1_hit`` is ``predicted_ncms[0] == expected_ncm``;
    ``top_3_hit`` is ``expected_ncm in predicted_ncms``.
    """

    case_id: str
    expected_ncm: str
    predicted_ncms: list[str]
    top_1_hit: bool
    top_3_hit: bool

    @model_validator(mode="after")
    def _exactly_three_predictions(self) -> "CaseResult":
        if len(self.predicted_ncms) != 3:
            raise ValueError(
                f"predicted_ncms must hold exactly 3 candidates, got {len(self.predicted_ncms)}"
            )
        return self


class EvalReport(BaseModel):
    """Aggregate accuracy over a whole EvalSuite run.

    ``top_1_accuracy``/``top_3_accuracy`` are derived from the hit counts, so
    they can never drift from ``top_1_hits``/``top_3_hits``. ``ece`` (Expected
    Calibration Error) is ``None`` in the walking skeleton: every candidate
    scores 0.0, so there is no probability distribution to calibrate.
    """

    total: int
    top_1_hits: int
    top_3_hits: int
    per_case: list[CaseResult]
    ece: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def top_1_accuracy(self) -> float:
        return self.top_1_hits / self.total if self.total else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def top_3_accuracy(self) -> float:
        return self.top_3_hits / self.total if self.total else 0.0
