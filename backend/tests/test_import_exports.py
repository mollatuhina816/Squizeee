import base64
import io
import pytest
from openpyxl import Workbook, load_workbook
from app.import_routes import parse_upload
from app.analytics_routes import export_report, safe_cell
from conftest import register


def test_import_preview_validation_and_idempotent_commit(client):
    org = register(client)["organization_id"]
    csv = b"kind,title,options,correct_answers\nmcq,Prime?,2|4,2\n"
    result = client.post(f"/api/v1/organizations/{org}/imports/preview", json={"format": "csv", "content_base64": base64.b64encode(csv).decode()})
    assert result.status_code == 200, result.text
    preview = result.json(); assert preview["can_commit"]
    path = f"/api/v1/organizations/{org}/imports/{preview['id']}/commit"
    assert client.post(path).json()["already_committed"] is False
    assert client.post(path).json()["already_committed"] is True
    assert len(client.get(f"/api/v1/organizations/{org}/bank/questions").json()) == 1


def test_import_errors_prevent_commit(client):
    org = register(client)["organization_id"]
    raw = b"kind,title,options,correct_answers\nmcq,Bad,A|B,Z\n"
    p = client.post(f"/api/v1/organizations/{org}/imports/preview", json={"format": "csv", "content_base64": base64.b64encode(raw).decode()}).json()
    assert p["errors"][0]["row"] == 2
    assert client.post(f"/api/v1/organizations/{org}/imports/{p['id']}/commit").status_code == 422


def test_xlsx_rejects_formulas():
    workbook = Workbook(); sheet = workbook.active
    sheet.append(["kind", "title"]); sheet.append(["content", "=HYPERLINK(1)"])
    out = io.BytesIO(); workbook.save(out)
    with pytest.raises(ValueError, match="Formula"):
        parse_upload(out.getvalue(), "xlsx")


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(1)", "  =1", "\tDDE"])
def test_export_formula_escaping(value):
    assert safe_cell(value).startswith("'")


def test_four_export_formats_are_readable():
    data = {"title": "A session", "participant_count": 1, "response_count": 1,
            "questions": [{"title": "=malicious", "responses": 1, "response_rate": 1, "accuracy": 0.5}],
            "individuals": [{"nickname": "=1+1", "responses": 1, "score": 1, "accuracy": 1}]}
    csv, _ = export_report(data, "csv"); assert b"'=malicious" in csv
    xlsx, _ = export_report(data, "xlsx")
    book = load_workbook(io.BytesIO(xlsx)); assert book["Participants"]["A2"].data_type == "s"
    pdf, _ = export_report(data, "pdf"); assert pdf.startswith(b"%PDF")
    png, _ = export_report(data, "png"); assert png.startswith(b"\x89PNG")


def test_oversized_body_rejected_before_parsing(client):
    response = client.post("/api/v1/auth/login", content=b"x" * 3_000_001, headers={"content-type": "application/json"})
    assert response.status_code == 413
