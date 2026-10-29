"""Quick smoke test for QR + OCR verification services.

Usage:
    python tests/test_certificate_services.py "path/to/certificate.pdf"
"""
import sys
from dataclasses import dataclass
from pathlib import Path

from app.services.verifier import verify_certificate


@dataclass
class RegistryRecord:
    certificate_id: str
    student_name: str
    course_name: str
    issuer: str
    issue_date: str
    credential_url: str
    status: str = "ACTIVE"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tests/test_certificate_services.py <certificate.pdf|image>")

    certificate_path = Path(sys.argv[1])
    record = RegistryRecord(
        certificate_id="4f4ba85bc1adb22bb04f",
        student_name="Akshay",
        course_name="AI In Process Intelligence Virtual Internship",
        issuer="Celonis / EduSkills",
        issue_date="June - August 2026",
        credential_url="https://certificate.eduskillsfoundation.org/verify/4f4ba85bc1adb22bb04f/4f4ba85bc1adb22bb04f",
    )

    result = verify_certificate(certificate_path, record)
    print("Result:", result["result"])
    print("Score:", result["score"])
    print("QR ID:", result["qr"].get("certificate_id"))
    print("OCR ID:", result["ocr"].get("fields", {}).get("certificate_id"))
    for reason in result["reasons"]:
        print("-", reason)

    if result["result"] != "VERIFIED":
        raise SystemExit(1)
