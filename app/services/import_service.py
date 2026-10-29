import hashlib
import json
from .qr_service import decode_qr
from .ocr_service import extract_ocr


def norm(value):
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def extract_certificate(file_path):
    qr = decode_qr(file_path)
    ocr = extract_ocr(file_path)
    parsed = qr.get("parsed_data") or {}
    fields = ocr.get("fields", {})

    certificate_id = qr.get("certificate_id") or parsed.get("certificate_id") or parsed.get("credential_id") or parsed.get("id") or fields.get("certificate_id")
    credential_url = qr.get("raw_data") if qr.get("payload_type") == "url" else parsed.get("credential_url") or parsed.get("verification_url") or ""
    recipient = parsed.get("recipient_name") or parsed.get("student_name") or parsed.get("name") or fields.get("recipient_name") or fields.get("student_name") or "Unknown"
    institution = parsed.get("institution_name") or parsed.get("college_name") or parsed.get("college") or parsed.get("university") or fields.get("institution_name") or ""

    extracted = {
        "certificate_id": certificate_id or "",
        "student_name": recipient,
        "recipient_name": recipient,
        "institution_name": institution,
        "student_id": parsed.get("student_id") or fields.get("student_id") or "",
        "course_name": parsed.get("course_name") or parsed.get("course") or parsed.get("program") or fields.get("course_name") or "Unknown",
        "issuer": parsed.get("issuer") or fields.get("issuer") or "Unknown",
        "issue_date": parsed.get("issue_date") or parsed.get("issued_at") or fields.get("issue_date") or "",
        "credential_url": credential_url,
    }
    confidence = 0
    if certificate_id: confidence += 55
    if qr.get("found"): confidence += 20
    if ocr.get("available"): confidence += 10
    confidence += min(15, sum(bool(extracted[k] and extracted[k] != "Unknown") for k in ["recipient_name", "institution_name", "course_name", "issuer"]) * 3.75)
    confidence = round(min(100, confidence), 1)
    return {"fields": extracted, "confidence": confidence, "qr": qr, "ocr": ocr}


def certificate_hash(fields):
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(file_path):
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
