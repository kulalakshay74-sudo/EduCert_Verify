from difflib import SequenceMatcher
import re

from .qr_service import decode_qr
from .ocr_service import extract_ocr


def normalize(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def normalize_id(value):
    return re.sub(r"[^a-z0-9]", "", normalize(value)) if value else ""


def similarity(a, b):
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 3)


def _field_value(field, qr, ocr):
    parsed = qr.get("parsed_data") or {}
    fields = ocr.get("fields", {})
    if field == "certificate_id":
        return qr.get("certificate_id") or parsed.get("certificate_id") or fields.get("certificate_id", "")
    if field == "recipient_name":
        return parsed.get("recipient_name") or parsed.get("student_name") or parsed.get("name") or fields.get("recipient_name") or fields.get("student_name", "")
    if field == "institution_name":
        return parsed.get("institution_name") or parsed.get("college_name") or parsed.get("college") or fields.get("institution_name", "")
    return parsed.get(field, "") or fields.get(field, "")


def verify_certificate(file_path, registry_record):
    qr = decode_qr(file_path)
    ocr = extract_ocr(file_path)

    checks = {}
    for field in ["certificate_id", "recipient_name", "institution_name", "student_id", "course_name", "issuer", "issue_date"]:
        source_value = _field_value(field, qr, ocr)
        registry_value = getattr(registry_record, field, "")
        if field == "certificate_id":
            matched = normalize_id(source_value) == normalize_id(registry_value) if source_value and registry_value else False
            sim = similarity(source_value, registry_value)
        else:
            matched = normalize(source_value) == normalize(registry_value) if source_value and registry_value else False
            sim = similarity(source_value, registry_value)
        checks[field] = {
            "source_value": source_value,
            "registry_value": registry_value,
            "match": matched,
            "similarity": sim,
        }

    cid_source = checks["certificate_id"]["source_value"]
    qr_id_match = checks["certificate_id"]["match"] and bool(cid_source)
    ocr_available = bool(ocr.get("available"))

    if registry_record.status != "ACTIVE":
        result = "REVOKED"
        score = 100 if qr_id_match else 0
        reasons = [f"Certificate registry status is {registry_record.status}."]
    elif qr_id_match:
        # A signed/issuer-generated QR that resolves to the exact registered ID is
        # the strongest identifier. OCR is used as corroboration, not as a reason
        # to reject a genuine QR URL because of OCR character errors.
        supporting_fields = [v for k, v in checks.items() if k != "certificate_id" and v["source_value"]]
        supporting_matches = sum(v["match"] for v in supporting_fields)
        score = round(70 + (30 * supporting_matches / len(supporting_fields)), 2) if supporting_fields else 100.0
        result = "VERIFIED"
        reasons = ["QR certificate ID exactly matches an active issuer registry record."]
        if qr.get("payload_type") == "url":
            reasons.append("QR contains a verification URL; the certificate ID was extracted from that URL.")
        if ocr_available:
            reasons.append("OCR was used as secondary certificate-content corroboration.")
    else:
        # No exact QR ID: allow a registry match through OCR only when the OCR ID
        # matches exactly after harmless punctuation/spacing normalization.
        ocr_id = ocr.get("fields", {}).get("certificate_id", "")
        ocr_match = normalize_id(ocr_id) == normalize_id(registry_record.certificate_id) if ocr_id else False
        if ocr_match and qr.get("found") is False:
            result = "VERIFIED_OCR"
            score = 85.0
            reasons = ["No readable QR was available, but OCR extracted the registered certificate ID."]
        elif not qr.get("found"):
            result = "QR_NOT_FOUND"
            score = 0
            reasons = ["A readable QR code was not found and no registered certificate ID could be confirmed by OCR."]
        else:
            result = "MISMATCH"
            score = 0
            reasons = ["QR certificate ID does not match the selected issuer registry record."]

    return {
        "result": result,
        "score": score,
        "qr": qr,
        "ocr": ocr,
        "checks": checks,
        "registry": {
            "certificate_id": registry_record.certificate_id,
            "student_name": registry_record.student_name,
            "recipient_name": registry_record.recipient_name or registry_record.student_name,
            "institution_name": registry_record.institution_name,
            "student_id": registry_record.student_id,
            "course_name": registry_record.course_name,
            "issuer": registry_record.issuer,
            "issue_date": registry_record.issue_date,
            "credential_url": registry_record.credential_url,
            "status": registry_record.status,
        },
        "reasons": reasons,
    }
