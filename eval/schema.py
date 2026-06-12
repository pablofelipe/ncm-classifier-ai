from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field, model_validator

ChapterCode = Annotated[str, Field(pattern=r"^\d{2}$")]


class EvalCase(BaseModel):
    id: str = Field(pattern=r"^case-\d{3}$")
    product_name: str = Field(max_length=100)
    product_description: str = Field(max_length=300)
    expected_ncm: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    # TIPI chapter where the correct answer actually lives (first 2 digits
    # of expected_ncm). Required.
    answer_chapter: ChapterCode
    # Chapters where the product could be wrongly classified.
    # Informational, for error analysis. Never contains answer_chapter.
    confusion_chapters: list[ChapterCode] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"]
    rationale: str = Field(min_length=20)
    source: Literal["ecommerce", "label", "invoice", "synthetic"]

    @model_validator(mode="after")
    def _answer_chapter_matches_ncm(self) -> "EvalCase":
        if self.answer_chapter != self.expected_ncm[:2]:
            raise ValueError(
                f"answer_chapter {self.answer_chapter!r} must match the first "
                f"two digits of expected_ncm {self.expected_ncm!r}"
            )
        return self

    @model_validator(mode="after")
    def _confusion_excludes_answer(self) -> "EvalCase":
        if self.answer_chapter in self.confusion_chapters:
            raise ValueError(
                f"confusion_chapters must not contain answer_chapter {self.answer_chapter!r}"
            )
        return self

    @model_validator(mode="after")
    def _confusion_chapters_unique(self) -> "EvalCase":
        if len(self.confusion_chapters) != len(set(self.confusion_chapters)):
            raise ValueError("confusion_chapters must not contain duplicates")
        return self


class EvalSuite(BaseModel):
    version: str
    tipi_version: str
    chapter_scope: ChapterCode
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
