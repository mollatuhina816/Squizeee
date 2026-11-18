import csv
import io
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import database
from .models import Answer, LiveSession, Participant, ParticipantProfile, Presentation, User, ScheduledQuiz, QuizAssignment
from .results import review_question
from .questions import Question, evaluate
from .security import identity

router = APIRouter(prefix="/api/v1", tags=["analytics"])


def answer_counts(details):
    return {name + '_count': sum(q['status'] == status for q in details if q['kind'] != 'content')
            for name, status in [('right', 'correct'), ('wrong', 'incorrect'), ('unanswered', 'unanswered'), ('ungraded', 'ungraded')]}


def report(db, user, session_id):
    from .builder_routes import access
    from .main import principal, require
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    presentation = access(db, user, session.organization_id, session.presentation_id)
    require(principal(db, user, session.organization_id), "analytics.read", owner_id=presentation.owner_id, department_id=presentation.department_id)
    participants = list(db.scalars(select(Participant).where(Participant.session_id == session_id)))
    answers = list(db.scalars(select(Answer).where(Answer.session_id == session_id)))
    questions = []
    for index, question in enumerate(session.questions):
        rows = [a for a in answers if a.question_index == index]
        scored = [a for a in rows if a.correct is not None]
        questions.append({"index": index, "title": question["title"], "kind": question["kind"], "responses": len(rows),
                          "response_rate": len(rows) / len(participants) if participants else 0,
                          "accuracy": sum(a.correct is True for a in scored) / len(scored) if scored else None})
    profiles = {p.id: p for p in db.scalars(select(ParticipantProfile).where(ParticipantProfile.id.in_([p.profile_id for p in participants if p.profile_id])))}
    individual = []
    for p in participants:
        rows = [a for a in answers if a.participant_id == p.id]
        scored = [a for a in rows if a.correct is not None]
        by_index = {a.question_index: a for a in rows}
        details = []
        for index, raw in enumerate(session.questions):
            answer = by_index.get(index)
            detail = review_question(index, raw, answer.value.get('answer') if answer else None, answer.correct if answer else None, answer.score if answer else 0)
            detail['elapsed_ms'] = answer.elapsed_ms if answer else None
            details.append(detail)
        profile = profiles.get(p.profile_id)
        individual.append({"id": str(p.id), "nickname": p.nickname, "email": profile.email if profile else None, "questions": details, **answer_counts(details), "responses": len(rows), "score": sum(a.score for a in rows) / 1000,
                           "accuracy": sum(a.correct is True for a in scored) / len(scored) if scored else None})
    scored_questions = [q for q in questions if q["accuracy"] is not None]
    answerable = sum(q["kind"] != "content" for q in session.questions)
    denominator = len(participants) * answerable
    return {"session_id": str(session.id), "title": presentation.title, "state": session.state, "record_type": "live", "created_at": session.created_at,
            "participant_count": len(participants), "response_count": len(answers),
            "response_rate": len(answers) / denominator if denominator else 0,
            "questions": questions, "individuals": individual,
            "hardest": min(scored_questions, key=lambda x: x["accuracy"]) if scored_questions else None,
            "easiest": max(scored_questions, key=lambda x: x["accuracy"]) if scored_questions else None}


@router.get("/organizations/{org_id}/sessions")
def history(org_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    from .main import principal, presentation_scope
    p = principal(db, user, org_id)
    if p.role == "faculty_lite" and "analytics.read" not in p.lite_permissions:
        raise HTTPException(403, "Permission denied")
    allowed = presentation_scope(select(Presentation.id), p)
    rows = db.execute(select(LiveSession, Presentation.title).join(Presentation, Presentation.id == LiveSession.presentation_id)
                      .where(LiveSession.presentation_id.in_(allowed)).order_by(LiveSession.created_at.desc()))
    records = [{"id": s.id, "title": title, "state": s.state, "created_at": s.created_at, "record_type": "live"} for s, title in rows]
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    scheduled = db.scalars(select(ScheduledQuiz).where(ScheduledQuiz.presentation_id.in_(allowed)).order_by(ScheduledQuiz.created_at.desc()))
    for quiz in scheduled:
        end = quiz.ends_at.replace(tzinfo=timezone.utc) if quiz.ends_at.tzinfo is None else quiz.ends_at
        start = quiz.starts_at.replace(tzinfo=timezone.utc) if quiz.starts_at.tzinfo is None else quiz.starts_at
        records.append({'id': quiz.id, 'title': quiz.title, 'created_at': quiz.created_at, 'record_type': 'assigned', 'state': 'ended' if now >= end else 'upcoming' if now < start else 'open'})
    return sorted(records, key=lambda r: r['created_at'].replace(tzinfo=timezone.utc), reverse=True)


@router.get("/sessions/{session_id}/analytics")
def analytics(session_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    return report(db, user, session_id)


@router.get('/scheduled-quizzes/{quiz_id}/analytics')
def assigned_analytics(quiz_id: uuid.UUID, user: User = Depends(identity), db: Session = Depends(database)):
    from .builder_routes import access
    from .main import principal, require
    from .scheduled_routes import expire_attempt
    quiz = db.get(ScheduledQuiz, quiz_id)
    if not quiz:
        raise HTTPException(404, 'Quiz not found')
    presentation = db.get(Presentation, quiz.presentation_id)
    access(db, user, presentation.organization_id, presentation.id)
    require(principal(db, user, presentation.organization_id), 'analytics.read', owner_id=presentation.owner_id, department_id=presentation.department_id)
    assignments = list(db.scalars(select(QuizAssignment).where(QuizAssignment.quiz_id == quiz_id).with_for_update()))
    for assignment in assignments:
        expire_attempt(quiz, assignment)
    db.commit()
    emails = [a.email for a in assignments]
    names = {u.email: u.name for u in db.scalars(select(User).where(User.email.in_(emails)))}
    individuals = []
    for assignment in assignments:
        values = assignment.answers if assignment.submitted_at else assignment.draft_answers
        values = values or []
        details = []
        for index, raw in enumerate(quiz.questions):
            answer = values[index] if index < len(values) else None
            correct, score = (None, 0) if answer is None else evaluate(Question(**raw), {'answer': answer}, 0)
            details.append(review_question(index, raw, answer, correct, score))
        scored = [q for q in details if q['correct'] is not None]
        individuals.append({'id': str(assignment.id), 'nickname': names.get(assignment.email, assignment.email), 'email': assignment.email,
                            'status': 'submitted' if assignment.submitted_at else 'in progress' if assignment.started_at else 'not started',
                            'score': sum(q['score'] for q in details) / 1000, 'responses': sum(q['answer'] is not None for q in details),
                            'accuracy': sum(q['correct'] is True for q in scored) / len(scored) if scored else None,
                            'questions': details, **answer_counts(details)})
    questions = []
    for index, raw in enumerate(quiz.questions):
        details = [p['questions'][index] for p in individuals]
        scored = [q for q in details if q['correct'] is not None]
        responses = sum(q['answer'] is not None for q in details)
        questions.append({'index': index, 'title': raw['title'], 'kind': raw['kind'], 'responses': responses,
                          'response_rate': responses / len(assignments) if assignments else 0,
                          'accuracy': sum(q['correct'] is True for q in scored) / len(scored) if scored else None})
    scored_questions = [q for q in questions if q['accuracy'] is not None]
    count = sum(p['responses'] for p in individuals)
    denominator = len(assignments) * len(questions)
    return {'session_id': str(quiz.id), 'record_type': 'assigned', 'title': quiz.title, 'created_at': quiz.created_at,
            'participant_count': len(assignments), 'response_count': count, 'response_rate': count / denominator if denominator else 0,
            'questions': questions, 'individuals': individuals,
            'hardest': min(scored_questions, key=lambda q: q['accuracy']) if scored_questions else None,
            'easiest': max(scored_questions, key=lambda q: q['accuracy']) if scored_questions else None}


def safe_cell(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def export_report(data, format):
    output = io.BytesIO()
    rows = [["Question", "Responses", "Response rate", "Accuracy"]]
    for q in data["questions"]:
        rows.append([safe_cell(q["title"]), q["responses"], q["response_rate"], q["accuracy"] if q["accuracy"] is not None else "N/A"])
    if format == "csv":
        text = io.StringIO(newline=""); writer = csv.writer(text); writer.writerows(rows)
        return text.getvalue().encode("utf-8-sig"), "text/csv"
    if format == "xlsx":
        from openpyxl import Workbook
        book = Workbook(); sheet = book.active; sheet.title = "Questions"
        for row in rows:
            sheet.append(row)
        sheet.freeze_panes = "A2"; sheet.column_dimensions["A"].width = 55
        people = book.create_sheet("Participants"); people.append(["Nickname", "Responses", "Score", "Accuracy"])
        for p in data["individuals"]:
            people.append([safe_cell(p["nickname"]), p["responses"], p["score"], p["accuracy"]])
        book.save(output)
        return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if format == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from xml.sax.saxutils import escape
        styles = getSampleStyleSheet()
        story = [Paragraph("Quizeee · Session report", styles["Title"]), Paragraph(escape(data["title"]), styles["Heading2"]),
                 Paragraph(f"Participants: {data['participant_count']} · Responses: {data['response_count']}", styles["Normal"]), Spacer(1, 18)]
        table_rows = [[Paragraph(escape(str(cell)), styles["Normal"]) for cell in row] for row in rows]
        table = Table(table_rows, colWidths=[270, 65, 85, 70], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce8ff")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
        story.append(table); SimpleDocTemplate(output).build(story)
        return output.getvalue(), "application/pdf"
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (1200, 300 + 45 * len(data["questions"])), "#f5f7fb")
    draw = ImageDraw.Draw(image)
    draw.text((40, 35), "QUIZEEE / SESSION SUMMARY", fill="#155eef", font_size=30)
    draw.text((40, 95), data["title"][:65], fill="#15233d", font_size=25)
    draw.text((40, 150), f"{data['participant_count']} participants | {data['response_count']} responses", fill="#526179", font_size=23)
    for index, q in enumerate(data["questions"]):
        y = 220 + index * 45
        draw.text((40, y), f"{index + 1}. {q['title'][:50]}", fill="#15233d", font_size=18)
        accuracy = q["accuracy"]
        draw.rectangle((650, y, 1050, y + 24), fill="#dbe2ed")
        if accuracy:
            draw.rectangle((650, y, 650 + int(400 * accuracy), y + 24), fill="#155eef")
        draw.text((1070, y), f"{accuracy:.0%}" if accuracy is not None else "N/A", fill="#15233d", font_size=18)
    image.save(output, format="PNG")
    return output.getvalue(), "image/png"


@router.get("/sessions/{session_id}/export/{format}")
def export(session_id: uuid.UUID, format: Literal["csv", "xlsx", "pdf", "png"], user: User = Depends(identity), db: Session = Depends(database)):
    data = report(db, user, session_id)
    content, mime = export_report(data, format)
    return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="quizeee-session-{session_id}.{format}"'})
