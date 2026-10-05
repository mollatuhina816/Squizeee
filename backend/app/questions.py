"""Canonical question contract shared by editor, bank, imports and session snapshots."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

KINDS = Literal["mcq", "multiple_select", "true_false", "short_answer", "ranking", "scale", "rating", "word_cloud", "poll", "quiz", "qa", "survey", "nps", "form", "content"]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: KINDS
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=5000)
    options: list[str] = Field(default_factory=list, max_length=20)
    correct_answers: list[str] = Field(default_factory=list, max_length=20)
    explanation: str = Field(default="", max_length=3000)
    marks: Decimal = Field(default=Decimal("1"), ge=0, le=1000, decimal_places=3)
    negative_marks: Decimal = Field(default=Decimal("0"), ge=0, le=1000, decimal_places=3)
    speed_bonus: Decimal = Field(default=Decimal("0"), ge=0, le=1000, decimal_places=3)
    duration_seconds: int = Field(default=30, ge=5, le=3600)
    minimum: int = Field(default=1, ge=-100, le=100)
    maximum: int = Field(default=5, ge=-100, le=100)

    @model_validator(mode="after")
    def validate_question(self):
        choice = self.kind in {"mcq", "multiple_select", "true_false", "ranking", "poll", "quiz"}
        if any(not x.strip() or len(x) > 300 for x in self.options):
            raise ValueError("Options must contain 1–300 characters")
        if len(set(self.options)) != len(self.options):
            raise ValueError("Options must be unique")
        if choice and len(self.options) < 2:
            raise ValueError("This question needs at least two options")
        if self.kind == "true_false" and self.options != ["True", "False"]:
            raise ValueError("True/False options must be True and False")
        if self.kind in {"mcq", "multiple_select", "true_false", "quiz"}:
            if not self.correct_answers or not set(self.correct_answers).issubset(self.options):
                raise ValueError("Choose correct answers from the options")
            if self.kind != "multiple_select" and len(self.correct_answers) != 1:
                raise ValueError("Select exactly one correct answer")
        if len(set(self.correct_answers)) != len(self.correct_answers):
            raise ValueError("Correct answers must be unique")
        if any(not x.strip() or len(x) > 300 for x in self.correct_answers):
            raise ValueError("Correct answers must contain 1–300 characters")
        if self.kind == "short_answer" and not self.correct_answers:
            raise ValueError("Provide at least one accepted answer")
        if self.minimum >= self.maximum:
            raise ValueError("Scale maximum must exceed minimum")
        return self

    def public(self):
        return self.model_dump(mode="json", exclude={"correct_answers", "explanation"})


def evaluate(question: Question, value: dict, elapsed_ms: int):
    """Validate a response and return correctness plus integer milli-mark score."""
    if set(value) != {"answer"}:
        raise ValueError("Expected an answer field")
    answer = value["answer"]
    kind = question.kind
    correct = None
    if kind in {"mcq", "quiz", "true_false", "poll"}:
        if not isinstance(answer, str) or answer not in question.options:
            raise ValueError("Select an available option")
        if kind != "poll":
            correct = answer in question.correct_answers
    elif kind in {"multiple_select", "ranking"}:
        if not isinstance(answer, list) or not answer or not all(isinstance(x, str) for x in answer):
            raise ValueError("Select available options")
        if len(set(answer)) != len(answer) or not set(answer).issubset(question.options):
            raise ValueError("Options must be unique and available")
        if kind == "ranking" and set(answer) != set(question.options):
            raise ValueError("Rank every option exactly once")
        if kind == "multiple_select":
            correct = set(answer) == set(question.correct_answers)
    elif kind in {"scale", "rating", "nps"}:
        low, high = (0, 10) if kind == "nps" else (question.minimum, question.maximum)
        if type(answer) is not int or not low <= answer <= high:
            raise ValueError("Rating is outside the allowed range")
    elif kind in {"short_answer", "word_cloud", "qa", "survey"}:
        limit = 80 if kind == "word_cloud" else 3000
        if not isinstance(answer, str) or not answer.strip() or len(answer) > limit:
            raise ValueError(f"Answer must contain 1–{limit} characters")
        if kind == "short_answer":
            correct = answer.strip().casefold() in {x.casefold() for x in question.correct_answers}
    else:
        raise ValueError("This slide does not accept live responses yet")
    score = 0
    if correct is True:
        remaining = max(0, question.duration_seconds * 1000 - elapsed_ms)
        bonus = question.speed_bonus * Decimal(remaining) / Decimal(question.duration_seconds * 1000)
        score = int((question.marks + bonus) * 1000)
    elif correct is False:
        score = -int(question.negative_marks * 1000)
    return correct, score
