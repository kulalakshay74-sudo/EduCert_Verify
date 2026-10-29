"""Integration tests for the admin bulk-import progress workflow."""
import json

import pytest

from app import create_app
from app.extensions import db
from app.models import Certificate, ImportBatch, ImportItem


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = (tmp_path / "educert-test.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin123")
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with app.app_context():
        db.drop_all()
        db.create_all()
    with app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session["admin"] = True
        yield test_client
    with app.app_context():
        db.session.remove()
        db.drop_all()


def fake_extract(path):
    # A deterministic OCR/QR substitute keeps this integration test independent
    # of local Tesseract installation and the visual content of test fixtures.
    filename = path.name
    cid = "CERT-001" if "first" in filename else "CERT-001"
    fields = {
        "certificate_id": cid,
        "student_name": "Test Student",
        "recipient_name": "Test Student",
        "institution_name": "Test Institute",
        "student_id": "S001",
        "course_name": "Test Course",
        "issuer": "Test Issuer",
        "issue_date": "2026-01-01",
        "credential_url": "",
    }
    return {
        "fields": fields,
        "confidence": 95.0,
        "qr": {"found": True},
        "ocr": {"confidence": 90.0, "text": "Test Student"},
    }


def test_bulk_import_reports_real_progress_and_duplicate_counts(client, monkeypatch):
    import app.routes as routes

    monkeypatch.setattr(routes, "extract_certificate", fake_extract)
    start = client.post("/admin/import/start", data={"total_files": "2"})
    assert start.status_code == 200
    batch_id = start.get_json()["batch_id"]

    first = client.post(
        f"/admin/import/{batch_id}/file",
        data={"certificate": ( __import__("io").BytesIO(b"fake image bytes"), "first.png")},
        content_type="multipart/form-data",
    )
    assert first.status_code == 200
    first_result = first.get_json()
    assert first_result["percent"] == 50
    assert first_result["processed"] == 1
    assert first_result["status"] == "IMPORTED"
    assert first_result["counts"]["imported"] == 1

    second = client.post(
        f"/admin/import/{batch_id}/file",
        data={"certificate": (__import__("io").BytesIO(b"fake image bytes"), "second.png")},
        content_type="multipart/form-data",
    )
    assert second.status_code == 200
    second_result = second.get_json()
    assert second_result["percent"] == 100
    assert second_result["processed"] == 2
    assert second_result["status"] == "DUPLICATE"
    assert second_result["counts"]["duplicates"] == 1

    with client.application.app_context():
        assert Certificate.query.count() == 1
        assert ImportBatch.query.get(batch_id).imported == 1
        items = ImportItem.query.filter_by(batch_id=batch_id).order_by(ImportItem.id).all()
        assert [item.status for item in items] == ["IMPORTED", "DUPLICATE"]


def test_bulk_import_rejects_invalid_batch_size(client):
    response = client.post("/admin/import/start", data={"total_files": "0"})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_bulk_import_requires_admin_session(tmp_path, monkeypatch):
    db_path = (tmp_path / "no-admin.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads-no-admin"))
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    response = app.test_client().post("/admin/import/start", data={"total_files": "1"})
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]
