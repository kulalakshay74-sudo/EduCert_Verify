import json
import re
from urllib.parse import urlparse

import cv2

from .document_service import get_image_paths


def _parse_qr_payload(data):
    parsed = None
    certificate_id = None
    payload_type = "text"

    try:
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            payload_type = "json"
            certificate_id = parsed.get("certificate_id") or parsed.get("credential_id") or parsed.get("id")
    except Exception:
        pass

    if not certificate_id:
        # Supports EduSkills/Celonis-style verification URLs such as:
        # https://certificate.eduskillsfoundation.org/verify/<id>/<id>
        try:
            parsed_url = urlparse(data.strip())
            if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
                segments = [s for s in parsed_url.path.split("/") if s]
                verify_index = next((i for i, s in enumerate(segments) if s.lower() in {"verify", "verification", "certificate"}), None)
                candidates = segments[verify_index + 1:] if verify_index is not None else segments
                if candidates:
                    certificate_id = candidates[0]
                    payload_type = "url"
        except Exception:
            pass

    # Generic fallback for URLs containing a certificate-like token.
    if not certificate_id:
        match = re.search(r"(?:certificate|credential|verify)[/_-]?([A-Za-z0-9-]{8,})", data, re.I)
        if match:
            certificate_id = match.group(1)
            payload_type = "url"

    return parsed, certificate_id, payload_type


def _decode_image(image_path):
    image = cv2.imread(str(image_path))
    if image is None:
        return None, None

    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(image)
    if data:
        return data, points

    # Try a grayscale/upscaled image for scanned PDFs and lower-quality certificates.
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    data, points, _ = detector.detectAndDecode(gray)
    return data, points


def decode_qr(file_path):
    try:
        image_paths = get_image_paths(file_path)
    except Exception as exc:
        return {"found": False, "error": str(exc), "pages_checked": 0}

    for page_number, image_path in enumerate(image_paths, start=1):
        data, points = _decode_image(image_path)
        if not data:
            continue

        parsed, certificate_id, payload_type = _parse_qr_payload(data)
        return {
            "found": True,
            "raw_data": data,
            "parsed_data": parsed,
            "certificate_id": certificate_id,
            "payload_type": payload_type,
            "format": "QR",
            "page": page_number,
        }

    return {"found": False, "error": "No readable QR code found.", "pages_checked": len(image_paths)}
