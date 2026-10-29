"""End-to-end Flask route tests for bulk certificate import progress.

Run with: python -m unittest discover -s tests -p "test_bulk_import_routes.py"
OCR/QR extraction is mocked so these tests do not require Tesseract or sample files.
"""
import io
import os
import tempfile
import unittest
from unittest.mock import patch


class BulkImportRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.old_db = os.environ.get("DATABASE_URL")
        cls.old_upload = os.environ.get("UPLOAD_DIR")
        os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(cls.temp.name, "test.db").replace("\\", "/")
        os.environ["UPLOAD_DIR"] = os.path.join(cls.temp.name, "uploads")
        from app import create_app
        from app.extensions import db
        cls.db = db
        cls.app = create_app()
        cls.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        if cls.old_db is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.old_db
        if cls.old_upload is None:
            os.environ.pop("UPLOAD_DIR", None)
        else:
            os.environ["UPLOAD_DIR"] = cls.old_upload
        cls.temp.cleanup()

    def setUp(self):
        with self.app.app_context():
            self.db.drop_all()
            self.db.create_all()
        with self.client.session_transaction() as session:
            session["admin"] = True

    @staticmethod
    def extracted(certificate_id):
        return {
            "fields": {
                "certificate_id": certificate_id,
                "student_name": "Test Student",
                "recipient_name": "Test Student",
                "institution_name": "Test College",
                "student_id": "TEST-001",
                "course_name": "Test Course",
                "issuer": "Test Issuer",
                "issue_date": "2026",
                "credential_url": "",
            },
            "confidence": 90,
            "qr": {"found": True},
            "ocr": {"confidence": 88, "text": "Test certificate"},
        }

    def start_batch(self, total):
        return self.client.post("/admin/import/start", data={"total_files": str(total)})

    def upload(self, batch_id, filename="certificate.png", content=b"fake image"):
        return self.client.post(
            f"/admin/import/{batch_id}/file",
            data={"certificate": (io.BytesIO(content), filename)},
            content_type="multipart/form-data",
        )

    def test_rejects_invalid_batch_size(self):
        response = self.start_batch(0)
        self.assertEqual(response.status_code, 400)

    def test_import_progress_increments_and_registry_persists(self):
        start = self.start_batch(2)
        self.assertEqual(start.status_code, 200)
        batch_id = start.get_json()["batch_id"]
        with patch("app.routes.extract_certificate", return_value=self.extracted("CERT-001")):
            first = self.upload(batch_id, "one.png", b"one")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["percent"], 50)
        self.assertEqual(first.get_json()["status"], "IMPORTED")
        with patch("app.routes.extract_certificate", return_value=self.extracted("CERT-002")):
            second = self.upload(batch_id, "two.png", b"two")
        self.assertEqual(second.status_code, 200)
        payload = second.get_json()
        self.assertEqual(payload["percent"], 100)
        self.assertEqual(payload["counts"]["imported"], 2)
        with self.app.app_context():
            from app.models import Certificate, ImportItem
            self.assertEqual(Certificate.query.count(), 2)
            self.assertEqual(ImportItem.query.filter_by(batch_id=batch_id).count(), 2)

    def test_duplicate_and_missing_id_are_counted(self):
        batch = self.start_batch(2).get_json()["batch_id"]
        with patch("app.routes.extract_certificate", return_value=self.extracted("CERT-DUP")):
            self.assertEqual(self.upload(batch, "first.png", b"first").get_json()["status"], "IMPORTED")
            duplicate = self.upload(batch, "second.png", b"second").get_json()
        self.assertEqual(duplicate["status"], "DUPLICATE")
        missing = self.extracted("")
        with patch("app.routes.extract_certificate", return_value=missing):
            # A new batch isolates the review outcome from the completed batch.
            review_batch = self.start_batch(1).get_json()["batch_id"]
            review = self.upload(review_batch, "review.png", b"review").get_json()
        self.assertEqual(review["status"], "NEEDS_REVIEW")
        self.assertEqual(review["counts"]["needs_review"], 1)

    def test_unsupported_file_is_recorded_as_failed(self):
        batch = self.start_batch(1).get_json()["batch_id"]
        result = self.upload(batch, "bad.exe", b"not a certificate").get_json()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["percent"], 100)
        self.assertEqual(result["counts"]["failed"], 1)

    def test_cannot_upload_more_files_than_batch_size(self):
        batch = self.start_batch(1).get_json()["batch_id"]
        with patch("app.routes.extract_certificate", return_value=self.extracted("CERT-END")):
            self.upload(batch, "one.png", b"one")
            extra = self.upload(batch, "extra.png", b"extra")
        self.assertEqual(extra.status_code, 409)


if __name__ == "__main__":
    unittest.main()
