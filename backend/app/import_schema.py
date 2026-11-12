"""Versioned interchange schema. Drafts may omit source answers; scored imports may not."""
from decimal import Decimal
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from .builder_routes import BankInput
from .questions import QuestionSource as Source


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Option(StrictModel):
    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=300)


class BaseQuestion(StrictModel):
    question: str = Field(min_length=1, max_length=500)
    body: str = Field(default='', max_length=5000)
    explanation: str = Field(default='', max_length=3000)
    source: Source = Field(default_factory=Source)
    answer_origin: Literal['source', 'missing', 'faculty', 'ai_suggested'] = 'missing'
    requires_review: bool = False
    marks: Decimal = Field(default=Decimal('1'), ge=0, le=1000, decimal_places=3)
    negative_marks: Decimal = Field(default=Decimal('0'), ge=0, le=1000, decimal_places=3)
    speed_bonus: Decimal = Field(default=Decimal('0'), ge=0, le=1000, decimal_places=3)
    duration_seconds: int = Field(default=30, ge=5, le=3600)
    subject: str = Field(default='', max_length=120)
    chapter: str = Field(default='', max_length=120)
    topic: str = Field(default='', max_length=120)
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    tags: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def unverified_answers(self):
        if self.answer_origin == 'ai_suggested':self.requires_review = True
        return self


class Choice(BaseQuestion):
    options: list[Option] = Field(min_length=2, max_length=20)
    @model_validator(mode='after')
    def unique_options(self):
        if len({o.id for o in self.options}) != len(self.options) or len({o.text for o in self.options}) != len(self.options):
            raise ValueError('Option IDs and texts must be unique')
        return self


class MCQ(Choice):
    type: Literal['mcq', 'quiz']
    correct_answers: list[str] = Field(default_factory=list, max_length=1)
    @model_validator(mode='after')
    def answer_options(self):
        if not set(self.correct_answers).issubset({o.id for o in self.options}):
            raise ValueError('Correct answers must reference option IDs')
        if not self.correct_answers: self.requires_review = True
        return self


class MultipleSelect(Choice):
    type: Literal['multiple_select']
    correct_answers: list[str] = Field(default_factory=list, max_length=20)
    @model_validator(mode='after')
    def answer_options(self):
        if len(set(self.correct_answers)) != len(self.correct_answers) or not set(self.correct_answers).issubset({o.id for o in self.options}):
            raise ValueError('Correct answers must reference unique option IDs')
        if not self.correct_answers: self.requires_review = True
        return self


class TrueFalse(MCQ):
    type: Literal['true_false']
    options: list[Option] = Field(default_factory=lambda: [Option(id='True', text='True'), Option(id='False', text='False')], min_length=2, max_length=2)
    @model_validator(mode='after')
    def boolean_options(self):
        if [o.text for o in self.options] != ['True', 'False']:
            raise ValueError('True/False options must be True and False')
        return self


class Survey(BaseQuestion):
    type: Literal['survey', 'poll']
    options: list[Option] = Field(default_factory=list, max_length=20)
    @model_validator(mode='after')
    def response_options(self):
        if self.options and len(self.options) < 2: raise ValueError('Supply at least two response options')
        if self.options and (len({o.id for o in self.options}) != len(self.options) or len({o.text for o in self.options}) != len(self.options)):
            raise ValueError('Response options must be unique')
        if self.type == 'poll' and not self.options: raise ValueError('A poll needs response options')
        return self


class ShortAnswer(BaseQuestion):
    type: Literal['short_answer']
    accepted_answers: list[str] = Field(default_factory=list, max_length=20)
    model_answer: str = Field(default='', max_length=3000)
    @model_validator(mode='after')
    def accepted_values(self):
        if any(not a or len(a) > 300 for a in self.accepted_answers) or len(set(self.accepted_answers)) != len(self.accepted_answers):
            raise ValueError('Accepted answers must be unique and contain 1-300 characters')
        return self


class Ranking(Choice):
    type: Literal['ranking']


class Scale(BaseQuestion):
    type: Literal['scale', 'rating', 'nps']
    minimum: int = Field(default=1, ge=-100, le=100)
    maximum: int = Field(default=5, ge=-100, le=100)
    @model_validator(mode='after')
    def range_values(self):
        if self.minimum >= self.maximum: raise ValueError('Scale maximum must exceed minimum')
        return self


class FreeResponse(BaseQuestion):
    type: Literal['word_cloud', 'qa', 'form', 'content']


CanonicalQuestion = Annotated[Union[MCQ, MultipleSelect, TrueFalse, Survey, ShortAnswer, Ranking, Scale, FreeResponse], Field(discriminator='type')]
question_adapter = TypeAdapter(CanonicalQuestion)


class CanonicalDocument(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    questions: list[CanonicalQuestion] = Field(max_length=500)


def to_bank(item: BaseQuestion, *, draft=False):
    raw = item.model_dump(mode='json')
    kind = raw['type']
    if kind == 'survey' and raw.get('options'): kind = 'poll' # Existing live option-response variant.
    options = {o['id']: o['text'] for o in raw.get('options', [])}
    question = {k: raw[k] for k in ['body', 'explanation', 'marks', 'negative_marks', 'speed_bonus', 'duration_seconds']}
    question.update(kind=kind, title=raw['question'], source=raw['source'], options=list(options.values()),
                    correct_answers=[options[a] for a in raw.get('correct_answers', [])] if options else raw.get('accepted_answers', []))
    if raw.get('model_answer'):question['model_answer']=raw['model_answer']
    if isinstance(item, Scale): question.update(minimum=item.minimum, maximum=item.maximum)
    row = {'question': question, **{k: raw[k] for k in ['subject', 'chapter', 'topic', 'difficulty', 'tags']}}
    if not draft: row = BankInput.model_validate(row).model_dump(mode='json')
    return row


def from_bank(row, source=None):
    q = row['question']; kind = q['kind']
    result = {k: v for k, v in q.items() if k not in {'kind', 'title', 'options', 'correct_answers', 'minimum', 'maximum', 'model_answer', 'source'}}
    result.update(type=kind, question=q['title'], source=source or q.get('source') or {}, **{k:v for k,v in row.items() if k != 'question'})
    if kind in {'mcq', 'multiple_select', 'quiz', 'true_false', 'ranking', 'poll', 'survey'}:
        result['options'] = [{'id': chr(65+i), 'text': text} for i,text in enumerate(q.get('options', []))]
    if kind in {'mcq', 'multiple_select', 'quiz', 'true_false'}:
        result['correct_answers'] = [o['id'] for o in result['options'] if o['text'] in q.get('correct_answers', [])]
    if kind == 'short_answer': result.update(accepted_answers=q.get('correct_answers', []),model_answer=q.get('model_answer',''))
    if kind in {'scale','rating','nps'}: result.update(minimum=q.get('minimum',1), maximum=q.get('maximum',5))
    result['answer_origin'] = 'source' if q.get('correct_answers') else 'missing'
    return question_adapter.validate_python(result)


def preview_row(item):
    row = to_bank(item, draft=True)
    row['canonical'] = item.model_dump(mode='json')
    row['requires_review'] = item.requires_review or item.answer_origin == 'ai_suggested'
    return row
