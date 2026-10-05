"""Private post-completion review; never used in public live snapshots."""
from .questions import Question


def review_question(index, raw, answer, correct, score):
    question = Question.model_validate(raw)
    return {"index": index, "kind": question.kind, "title": question.title, "body": question.body,
            "options": question.options, "correct_answers": question.correct_answers,
            "explanation": question.explanation, "answer": answer, "correct": correct,
            "score": score, "marks": int(question.marks * 1000),
            "status": "unanswered" if answer is None else "correct" if correct is True else "incorrect" if correct is False else "ungraded"}
