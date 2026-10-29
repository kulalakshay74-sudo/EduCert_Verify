from datetime import datetime
from .extensions import db


class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    certificate_id = db.Column(db.String(120), unique=True, nullable=False, index=True)
    student_name = db.Column(db.String(200), nullable=False, default="Unknown")
    recipient_name = db.Column(db.String(200))
    institution_name = db.Column(db.String(300))
    student_id = db.Column(db.String(120))
    course_name = db.Column(db.String(250), nullable=False, default="Unknown")
    issuer = db.Column(db.String(250), nullable=False, default="Unknown")
    issue_date = db.Column(db.String(80))
    credential_url = db.Column(db.String(500))
    certificate_hash = db.Column(db.String(64), nullable=False, index=True)
    source_file_hash = db.Column(db.String(64), index=True)
    status = db.Column(db.String(30), default="ACTIVE", index=True)
    source_filename = db.Column(db.String(300))
    source_path = db.Column(db.String(700))
    extraction_method = db.Column(db.String(80), default="AUTO")
    extraction_confidence = db.Column(db.Float, default=0)
    ocr_confidence = db.Column(db.Float, default=0)
    extraction_version = db.Column(db.String(30), default="2.0")
    raw_ocr = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ImportBatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_files = db.Column(db.Integer, default=0)
    imported = db.Column(db.Integer, default=0)
    duplicates = db.Column(db.Integer, default=0)
    needs_review = db.Column(db.Integer, default=0)
    failed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class ImportItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("import_batch.id"), index=True)
    filename = db.Column(db.String(300), nullable=False)
    certificate_id = db.Column(db.String(120))
    status = db.Column(db.String(40), nullable=False)
    message = db.Column(db.String(500))
    extracted_json = db.Column(db.Text)
    source_path = db.Column(db.String(700))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class VerificationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    certificate_id = db.Column(db.String(120), index=True)
    result = db.Column(db.String(40), nullable=False, index=True)
    score = db.Column(db.Float, default=0)
    details_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
