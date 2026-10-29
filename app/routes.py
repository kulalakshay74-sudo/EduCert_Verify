import csv
import io
import json
import os
import secrets
from pathlib import Path
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Certificate, VerificationLog, ImportBatch, ImportItem
from .services.verifier import verify_certificate
from .services.qr_service import decode_qr
from .services.ocr_service import extract_ocr
from .services.import_service import extract_certificate, certificate_hash, file_hash, norm

web = Blueprint("web", __name__)
api = Blueprint("api", __name__)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).resolve().parent.parent / "data" / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED = {"png", "jpg", "jpeg", "webp", "bmp", "pdf"}


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("web.admin_login"))
        return fn(*args, **kwargs)
    return wrapper


def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED


def _candidate_certificate_id(qr, ocr):
    return qr.get("certificate_id") or (qr.get("parsed_data") or {}).get("certificate_id") or ocr.get("fields", {}).get("certificate_id")


def _find_certificate(cid):
    if not cid:
        return None
    exact = Certificate.query.filter_by(certificate_id=cid).first()
    if exact:
        return exact
    key = norm(cid)
    return next((c for c in Certificate.query.all() if norm(c.certificate_id) == key), None)


def _verify_file(path):
    qr = decode_qr(path)
    ocr = extract_ocr(path)
    cid = _candidate_certificate_id(qr, ocr)
    record = _find_certificate(cid)
    if record:
        return cid, verify_certificate(path, record)
    return cid, {
        "result": "UNREGISTERED", "score": 0, "qr": qr, "ocr": ocr, "registry": {}, "checks": {},
        "reasons": ["No matching certificate exists in the local issuer registry.", "An administrator must import the certificate into the registry before it can be matched."]
    }


def _save_upload(file, prefix=""):
    filename = secure_filename(file.filename)
    path = UPLOAD_DIR / f"{prefix}{secrets.token_hex(8)}_{filename}"
    file.save(path)
    return path, filename


@web.get("/")
def index():
    return render_template("index.html")


@web.post("/verify")
def verify_page():
    file = request.files.get("certificate")
    if not file or not file.filename:
        flash("Please select a certificate PDF or image.", "error")
        return redirect(url_for("web.index"))
    if not allowed_file(file.filename):
        flash("Allowed files: PDF, PNG, JPG, JPEG, WEBP, BMP.", "error")
        return redirect(url_for("web.index"))
    path, _ = _save_upload(file)
    cid, result = _verify_file(path)
    db.session.add(VerificationLog(certificate_id=cid, result=result["result"], score=result["score"], details_json=json.dumps(result)))
    db.session.commit()
    return render_template("result.html", result=result)


@web.get("/admin/login")
def admin_login():
    return render_template("admin_login.html")


@web.post("/admin/login")
def admin_login_post():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    if secrets.compare_digest(username, os.getenv("ADMIN_USERNAME", "admin")) and secrets.compare_digest(password, os.getenv("ADMIN_PASSWORD", "admin123")):
        session["admin"] = True
        return redirect(url_for("web.admin"))
    flash("Invalid admin credentials.", "error")
    return redirect(url_for("web.admin_login"))


@web.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("web.index"))


@web.get("/admin")
@admin_required
def admin():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "ALL")
    base = Certificate.query
    if query:
        like = f"%{query}%"
        from sqlalchemy import or_
        base = base.filter(or_(Certificate.certificate_id.ilike(like), Certificate.student_name.ilike(like), Certificate.recipient_name.ilike(like), Certificate.institution_name.ilike(like), Certificate.course_name.ilike(like), Certificate.issuer.ilike(like)))
    if status in {"ACTIVE", "REVOKED"}:
        base = base.filter_by(status=status)
    certificates = base.order_by(Certificate.created_at.desc()).all()
    logs = VerificationLog.query.order_by(VerificationLog.created_at.desc()).limit(15).all()
    batches = ImportBatch.query.order_by(ImportBatch.created_at.desc()).limit(8).all()
    session["review_count"] = ImportItem.query.filter_by(status="NEEDS_REVIEW").count()
    stats = {
        "review": session["review_count"],
        "total": Certificate.query.count(),
        "active": Certificate.query.filter_by(status="ACTIVE").count(),
        "revoked": Certificate.query.filter_by(status="REVOKED").count(),
        "verified": VerificationLog.query.filter_by(result="VERIFIED").count(),
    }
    return render_template("admin.html", certificates=certificates, logs=logs, batches=batches, stats=stats, query=query, status=status)


@web.post("/admin/import")
@admin_required
def bulk_import():
    files = [f for f in request.files.getlist("certificates") if f and f.filename]
    max_files = int(os.getenv("MAX_BULK_FILES", "100"))
    if not files:
        flash("Select one or more certificate files.", "error")
        return redirect(url_for("web.admin"))
    if len(files) > max_files:
        flash(f"Maximum {max_files} certificates per batch.", "error")
        return redirect(url_for("web.admin"))

    batch = ImportBatch(total_files=len(files))
    db.session.add(batch)
    db.session.flush()

    for file in files:
        item_status = "FAILED"
        message = ""
        extracted = {}
        cid = ""
        path = None
        try:
            if not allowed_file(file.filename):
                raise ValueError("Unsupported file type")
            path, original_name = _save_upload(file, prefix="registry_")
            result = extract_certificate(path)
            extracted = result["fields"]
            cid = extracted.get("certificate_id", "")
            if not cid:
                batch.needs_review += 1
                item_status = "NEEDS_REVIEW"
                message = "Certificate ID could not be extracted from QR/OCR."
            else:
                existing = _find_certificate(cid)
                if existing:
                    batch.duplicates += 1
                    item_status = "DUPLICATE"
                    message = f"Already registered as {existing.certificate_id}."
                else:
                    values = extracted.copy()
                    values["certificate_hash"] = certificate_hash(values)
                    values["source_file_hash"] = file_hash(path)
                    values["extraction_version"] = "2.0"
                    values.update({
                        "source_filename": original_name,
                        "source_path": str(path),
                        "extraction_method": "QR+OCR" if result["qr"].get("found") else "OCR",
                        "extraction_confidence": result["confidence"],
                        "raw_ocr": result["ocr"].get("text", ""),
                        "status": "ACTIVE",
                    })
                    db.session.add(Certificate(**values))
                    batch.imported += 1
                    item_status = "IMPORTED"
                    message = f"Imported automatically with {result['confidence']}% extraction confidence."
        except Exception as exc:
            batch.failed += 1
            message = str(exc)[:490]
        db.session.add(ImportItem(batch_id=batch.id, filename=file.filename, certificate_id=cid or None, status=item_status, message=message, extracted_json=json.dumps(extracted), source_path=str(path) if path else None))

    db.session.commit()
    flash(f"Bulk import complete: {batch.imported} imported, {batch.duplicates} duplicates, {batch.needs_review} need review, {batch.failed} failed.", "success")
    return redirect(url_for("web.admin"))


@web.post("/admin/certificates/<int:cert_id>/reprocess")
@admin_required
def reprocess(cert_id):
    cert = Certificate.query.get_or_404(cert_id)
    if not cert.source_path or not Path(cert.source_path).exists():
        flash("Original uploaded file is no longer available. The persistent registry record was kept.", "error")
        return redirect(url_for("web.admin"))
    result = extract_certificate(cert.source_path)
    fields = result["fields"]
    if fields.get("certificate_id") and norm(fields["certificate_id"]) != norm(cert.certificate_id):
        flash("Re-extraction found a different certificate ID; record was not overwritten.", "error")
        return redirect(url_for("web.admin"))
    cert.student_name = fields.get("student_name") or cert.student_name
    cert.recipient_name = fields.get("recipient_name") or cert.recipient_name or cert.student_name
    cert.institution_name = fields.get("institution_name") or cert.institution_name
    cert.student_id = fields.get("student_id") or cert.student_id
    cert.course_name = fields.get("course_name") or cert.course_name
    cert.issuer = fields.get("issuer") or cert.issuer
    cert.issue_date = fields.get("issue_date") or cert.issue_date
    cert.credential_url = fields.get("credential_url") or cert.credential_url
    cert.extraction_confidence = result["confidence"]
    cert.extraction_version = "2.0"
    cert.raw_ocr = result["ocr"].get("text", "")
    db.session.commit()
    flash(f"Re-extracted {cert.certificate_id}: recipient and institution fields refreshed.", "success")
    return redirect(url_for("web.admin"))

@web.post("/admin/certificates/<int:cert_id>/revoke")
@admin_required
def revoke(cert_id):
    c = Certificate.query.get_or_404(cert_id)
    c.status = "REVOKED"
    db.session.commit()
    flash(f"Certificate {c.certificate_id} revoked.", "success")
    return redirect(url_for("web.admin"))


@web.post("/admin/certificates/<int:cert_id>/activate")
@admin_required
def activate(cert_id):
    c = Certificate.query.get_or_404(cert_id)
    c.status = "ACTIVE"
    db.session.commit()
    flash(f"Certificate {c.certificate_id} activated.", "success")
    return redirect(url_for("web.admin"))


@web.get("/admin/review")
@admin_required
def review_dashboard():
    items = ImportItem.query.filter_by(status="NEEDS_REVIEW").order_by(ImportItem.created_at.desc()).all()
    stats = {
        "pending": len(items),
        "total": ImportItem.query.filter_by(status="NEEDS_REVIEW").count(),
        "imported": ImportItem.query.filter_by(status="IMPORTED").count(),
        "duplicates": ImportItem.query.filter_by(status="DUPLICATE").count(),
        "failed": ImportItem.query.filter_by(status="FAILED").count(),
    }
    return render_template("review.html", items=items, stats=stats)


@web.post("/admin/review/<int:item_id>/reextract")
@admin_required
def review_reextract(item_id):
    item = ImportItem.query.get_or_404(item_id)
    if item.status != "NEEDS_REVIEW":
        flash("This review item is no longer pending.", "error")
        return redirect(url_for("web.review_dashboard"))
    if not item.source_path or not Path(item.source_path).exists():
        flash("Original uploaded file is unavailable. Keep the item for manual follow-up.", "error")
        return redirect(url_for("web.review_dashboard"))
    result = extract_certificate(item.source_path)
    item.extracted_json = json.dumps(result["fields"], ensure_ascii=False)
    item.message = f"Re-extracted at {result['confidence']}% confidence."
    if result["fields"].get("certificate_id"):
        item.certificate_id = result["fields"]["certificate_id"]
        flash("Certificate ID was found. Review it and approve/register.", "success")
    else:
        item.message = "Certificate ID is still missing after re-extraction."
        flash("Still needs review: certificate ID could not be extracted.", "error")
    db.session.commit()
    return redirect(url_for("web.review_dashboard"))


@web.post("/admin/review/<int:item_id>/approve")
@admin_required
def review_approve(item_id):
    item = ImportItem.query.get_or_404(item_id)
    if item.status != "NEEDS_REVIEW":
        flash("This review item is no longer pending.", "error")
        return redirect(url_for("web.review_dashboard"))
    try:
        extracted = json.loads(item.extracted_json or "{}")
    except Exception:
        extracted = {}
    cid = extracted.get("certificate_id") or item.certificate_id
    if not cid:
        flash("Cannot approve: certificate ID is missing.", "error")
        return redirect(url_for("web.review_dashboard"))
    existing = _find_certificate(cid)
    if existing:
        item.status = "DUPLICATE"
        item.message = f"Already registered as {existing.certificate_id}."
        db.session.commit()
        flash("This certificate already exists in the registry.", "error")
        return redirect(url_for("web.review_dashboard"))
    if not item.source_path or not Path(item.source_path).exists():
        flash("Original uploaded file is unavailable; cannot safely register it.", "error")
        return redirect(url_for("web.review_dashboard"))
    try:
        values = dict(extracted)
        values["certificate_hash"] = certificate_hash(values)
        values["source_file_hash"] = file_hash(item.source_path)
        values.update({
            "source_filename": item.filename,
            "source_path": item.source_path,
            "extraction_method": "QR+OCR" if (extract_certificate(item.source_path)["qr"].get("found")) else "OCR",
            "extraction_confidence": 100 if cid else 0,
            "extraction_version": "3.0",
            "raw_ocr": "",
            "status": "ACTIVE",
        })
        # Avoid Unknown/null values violating model defaults.
        values["student_name"] = values.get("student_name") or values.get("recipient_name") or "Unknown"
        values["recipient_name"] = values.get("recipient_name") or values["student_name"]
        values["course_name"] = values.get("course_name") or "Unknown"
        values["issuer"] = values.get("issuer") or "Unknown"
        db.session.add(Certificate(**values))
        item.status = "IMPORTED"
        item.message = "Approved from Review Queue and registered."
        db.session.commit()
        flash(f"{cid} approved and added to the registry.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Approval failed: {str(exc)[:250]}", "error")
    return redirect(url_for("web.review_dashboard"))


@web.post("/admin/review/<int:item_id>/dismiss")
@admin_required
def review_dismiss(item_id):
    item = ImportItem.query.get_or_404(item_id)
    item.status = "DISMISSED"
    item.message = "Dismissed by administrator."
    db.session.commit()
    flash(f"{item.filename} removed from the active review queue.", "success")
    return redirect(url_for("web.review_dashboard"))


@web.get("/admin/imports/<int:batch_id>")
@admin_required
def import_details(batch_id):
    batch = ImportBatch.query.get_or_404(batch_id)
    items = ImportItem.query.filter_by(batch_id=batch.id).order_by(ImportItem.id.desc()).all()
    return render_template("import_details.html", batch=batch, items=items)


@web.get("/admin/export.csv")
@admin_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Certificate ID", "Recipient Name", "College / Institution", "Student ID", "Course", "Issuer", "Issue Date", "Credential URL", "Status", "Confidence", "Source File", "Created At"])
    for c in Certificate.query.order_by(Certificate.created_at.desc()).all():
        writer.writerow([c.certificate_id, c.recipient_name or c.student_name, c.institution_name or "", c.student_id or "", c.course_name, c.issuer, c.issue_date or "", c.credential_url or "", c.status, c.extraction_confidence, c.source_filename or "", c.created_at])
    return send_file(io.BytesIO(output.getvalue().encode("utf-8-sig")), mimetype="text/csv", as_attachment=True, download_name="educert_registry.csv")


@api.get("/health")
def health():
    return jsonify({"status": "ok", "service": "EduCert Verify API"})


@api.post("/verify")
def api_verify():
    file = request.files.get("certificate")
    if not file or not file.filename:
        return jsonify({"error": "multipart field 'certificate' is required"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "unsupported file type; use PDF/PNG/JPG/JPEG/WEBP/BMP"}), 400
    path, _ = _save_upload(file, prefix="api_")
    cid, result = _verify_file(path)
    db.session.add(VerificationLog(certificate_id=cid, result=result["result"], score=result["score"], details_json=json.dumps(result)))
    db.session.commit()
    return jsonify(result)


@api.get("/certificates/<certificate_id>")
def certificate_lookup(certificate_id):
    c = _find_certificate(certificate_id)
    if not c:
        return jsonify({"found": False}), 404
    return jsonify({"found": True, "certificate": {
        "certificate_id": c.certificate_id, "student_name": c.student_name, "recipient_name": c.recipient_name or c.student_name, "institution_name": c.institution_name, "student_id": c.student_id,
        "course_name": c.course_name, "issuer": c.issuer, "issue_date": c.issue_date,
        "credential_url": c.credential_url, "status": c.status, "certificate_hash": c.certificate_hash,
        "extraction_confidence": c.extraction_confidence,
    }})
