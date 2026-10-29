import re
import cv2

try:
    import pytesseract
except Exception:
    pytesseract = None

from .document_service import get_image_paths

FIELD_PATTERNS = {
    "certificate_id": [
        r"certificate\s*(?:id|no|number)\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{7,})",
        r"credential\s*(?:id|no|number)\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{7,})",
    ],
    "student_id": [r"student\s*(?:id|no|number)\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{5,})"],
    "recipient_name": [
        r"(?:recipient|recipient\s*name|student\s*name)\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{2,})"
    ],
    "institution_name": [
        r"(?:institution|institution\s*name|college|college\s*name|university|school)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 &.,'()\/-]{3,})"
    ],
    "course_name": [
        r"(?:course|program|certification|internship)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 &+./()_-]{3,})"
    ],
    "issue_date": [
        r"(?:issue\s*date|date\s*of\s*issue|issued)\s*[:\-]?\s*([0-9]{1,4}[-/.][0-9]{1,2}[-/.][0-9]{1,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})"
    ],
}


def _clean_line(line):
    return re.sub(r"\s+", " ", line).strip(" |:;,-")


def _extract_fields(text):
    fields = {}
    for field, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                value = _clean_line(match.group(1))
                if value:
                    fields[field] = value
                    break

    lines = [_clean_line(x) for x in text.splitlines() if _clean_line(x)]
    lower_lines = [x.lower() for x in lines]

    # Issuer: prefer explicit issuer/supporting-organization wording.
    for line in lines:
        low = line.lower()
        if "supported by" in low:
            value = _clean_line(re.sub(r".*supported by", "", line, flags=re.I))
            if value:
                fields.setdefault("issuer", value)
        elif "issued by" in low:
            value = _clean_line(re.sub(r".*issued by", "", line, flags=re.I))
            if value:
                fields.setdefault("issuer", value)

    if "issuer" not in fields:
        hits = [line for line in lines if any(x in line.lower() for x in ["eduskills", "celonis", "microsoft", "aws", "google", "oracle"])]
        if hits:
            joined = " ".join(hits).lower()
            if "celonis" in joined and "eduskills" in joined:
                fields["issuer"] = "Celonis / EduSkills"
            elif "eduskills" in joined:
                fields["issuer"] = "EduSkills"
            elif "celonis" in joined:
                fields["issuer"] = "Celonis"

    # Certificate ID fallback.
    if "certificate_id" not in fields:
        m = re.search(r"certificate\s*id\s*[:#-]?\s*([A-Za-z0-9_-]{8,})", text, re.I)
        if m:
            fields["certificate_id"] = m.group(1).strip()

    # Structured certificate layout fallback used by many academic certificates:
    # "This is to certify that" -> recipient -> institution -> completion/course.
    for i, line in enumerate(lines):
        if "certify that" in line.lower():
            if i + 1 < len(lines):
                candidate = lines[i + 1]
                if 1 <= len(candidate.split()) <= 6 and not _is_noise(candidate):
                    fields.setdefault("recipient_name", candidate)
            if i + 2 < len(lines):
                candidate = lines[i + 2]
                if _looks_like_institution(candidate):
                    fields.setdefault("institution_name", candidate)

    # Alternative common layout: title, explanatory line, recipient, institution.
    if "recipient_name" not in fields:
        for i, line in enumerate(lines):
            if "certificate of" in line.lower() and i + 2 < len(lines):
                candidate = lines[i + 2]
                if 1 <= len(candidate.split()) <= 6 and not _is_noise(candidate):
                    fields["recipient_name"] = candidate
                    if i + 3 < len(lines) and _looks_like_institution(lines[i + 3]):
                        fields.setdefault("institution_name", lines[i + 3])
                    break

    if "institution_name" not in fields:
        for line in lines:
            if _looks_like_institution(line):
                fields["institution_name"] = line
                break

    # Prefer the course line immediately following completion wording.
    if fields.get("course_name", "").lower() in {"this is to certify that", "certificate", "certificate of virtual internship"}:
        fields.pop("course_name", None)
    if "course_name" not in fields:
        for i, line in enumerate(lines):
            low = line.lower()
            if "successfully completed" in low:
                for candidate in lines[i + 1:i + 4]:
                    candidate_low = candidate.lower()
                    if any(k in candidate_low for k in ["internship", "course", "training", "certification"]):
                        if not any(k in candidate_low for k in ["certificate of", "supported by", "education internship"]):
                            fields["course_name"] = candidate
                            break
                if "course_name" in fields:
                    break
    if "course_name" not in fields:
        for line in lines:
            low = line.lower()
            if any(k in low for k in ["internship", "certification", "course", "training"]):
                if not any(k in low for k in ["certificate of", "supported by", "education internship", "this is to certify"]):
                    fields["course_name"] = line
                    break

    if "issue_date" not in fields:
        for line in lines:
            if re.search(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b.*\b20\d{2}\b", line, re.I):
                fields["issue_date"] = line
                break

    # Small OCR normalization for the common AI label where Tesseract reads capital I as l.
    if fields.get("course_name", "").startswith("Al "):
        fields["course_name"] = "AI " + fields["course_name"][3:]

    # Backward-compatible aliases.
    if fields.get("recipient_name") and not fields.get("student_name"):
        fields["student_name"] = fields["recipient_name"]
    return fields


def _is_noise(value):
    low = value.lower()
    return any(k in low for k in ["internship", "student id", "certificate id", "srinivas institute", "has successfully"])


def _looks_like_institution(value):
    low = value.lower()
    markers = ["institute", "institution", "college", "university", "school", "academy", "technical", "technology"]
    return 1 <= len(value.split()) <= 12 and any(m in low for m in markers)


def extract_ocr(file_path):
    if pytesseract is None:
        return {"available": False, "text": "", "fields": {}, "error": "pytesseract is not installed."}
    try:
        image_paths = get_image_paths(file_path)
    except Exception as exc:
        return {"available": False, "text": "", "fields": {}, "error": str(exc)}

    page_results, all_text, combined_fields = [], [], {}
    for page_number, image_path in enumerate(image_paths, start=1):
        image = cv2.imread(str(image_path))
        if image is None:
            continue
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # Denoise and threshold a working copy to improve recognition on scans.
            gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            text = pytesseract.image_to_string(processed)
            data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            return {"available": False, "text": "", "fields": {}, "error": f"Tesseract unavailable: {exc}"}

        word_scores = []
        scored_words = []
        for word, raw_conf in zip(data.get("text", []), data.get("conf", [])):
            word = (word or "").strip()
            try:
                score = float(raw_conf)
            except (TypeError, ValueError):
                continue
            if word and score >= 0:
                word_scores.append(score)
                scored_words.append({"word": word, "confidence": round(score, 1)})

        page_confidence = round(sum(word_scores) / len(word_scores), 1) if word_scores else 0.0
        fields = _extract_fields(text)
        field_confidence = {}
        for key, value in fields.items():
            value_tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", str(value)) if len(token) > 1}
            matches = [item["confidence"] for item in scored_words if item["word"].lower().strip(".,:;()") in value_tokens]
            field_confidence[key] = round(sum(matches) / len(matches), 1) if matches else page_confidence
        all_text.append(text)
        combined_fields.update({k: v for k, v in fields.items() if v})
        page_results.append({
            "page": page_number, "fields": fields, "field_confidence": field_confidence,
            "confidence": page_confidence, "words_detected": len(word_scores),
            "word_count": len(text.split()),
        })

    if not all_text:
        return {"available": False, "text": "", "fields": {}, "error": "No readable certificate pages found."}
    total_words = sum(page["words_detected"] for page in page_results)
    overall_confidence = round(
        sum(page["confidence"] * page["words_detected"] for page in page_results) / total_words, 1
    ) if total_words else 0.0
    combined_field_confidence = {}
    for page in page_results:
        combined_field_confidence.update(page["field_confidence"])
    return {
        "available": True,
        "text": "\n\n--- PAGE BREAK ---\n\n".join(all_text),
        "fields": combined_fields,
        "pages": page_results,
        "confidence": overall_confidence,
        "field_confidence": combined_field_confidence,
        "words_detected": total_words,
        "pages_processed": len(page_results),
        "pipeline": [
            {"name": "Document loading", "status": "complete"},
            {"name": "Image preprocessing", "status": "complete"},
            {"name": "Text recognition", "status": "complete"},
            {"name": "Field extraction", "status": "complete"},
            {"name": "Confidence analysis", "status": "complete"},
        ],
    }
