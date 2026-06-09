from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

ChapterCode = Annotated[str, Field(pattern=r"^\d{2}$")]


class EvalCase(BaseModel):
    id: str = Field(pattern=r"^case-\d{3}$")
    product_name: str = Field(max_length=100)
    product_description: str = Field(max_length=300)
    expected_ncm: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    # Capítulo TIPI onde a resposta correta de fato vive (2 primeiros dígitos
    # de expected_ncm). Obrigatório.
    answer_chapter: ChapterCode
    # Capítulos onde o produto poderia ser erroneamente classificado.
    # Informacional, para análise de erros. Nunca contém answer_chapter.
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
                f"confusion_chapters must not contain answer_chapter "
                f"{self.answer_chapter!r}"
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
