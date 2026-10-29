# EduCert Verify

Professional certificate verification and **bulk credential ingestion** platform built with Flask, SQLite, OpenCV QR scanning, PyMuPDF and Tesseract OCR.

## What changed in the automated registry version

The Admin Portal no longer requires one-by-one manual certificate registration.

### Bulk certificate import

Upload up to `MAX_BULK_FILES` certificates at once. Each file is automatically:

1. Saved to the protected local upload area.
2. Rendered page-by-page when it is a PDF.
3. Scanned for a QR code.
4. Parsed as JSON or a verification URL.
5. Processed with OCR.
6. Parsed for certificate ID, student name, student ID, course/program, issuer and issue date.
7. Given an extraction confidence score.
8. Checked for duplicate certificate IDs.
9. Added to the registry automatically when a certificate ID is available.
10. Added to an import audit trail.

Files that cannot yield a certificate ID are **NEEDS_REVIEW** rather than silently being discarded.

### OCR Studio and confidence analytics

The Admin Portal includes a dedicated **OCR Studio** at `/admin/ocr-studio`. Upload a PDF or image to inspect recognition output before using it in the registry.

- Overall OCR confidence calculated from Tesseract's word-level confidence output.
- Per-page confidence and detected-word counts for multi-page PDFs.
- Field-level confidence indicators for extracted certificate fields.
- Visible processing pipeline: document loading, image preprocessing, text recognition, field extraction and confidence analysis.
- Image denoising and Otsu thresholding before OCR.
- Full extracted text, field summary and responsive analysis UI.
- Downloadable JSON OCR report and plain-text OCR output.
- OCR and extraction confidence shown as separate values in the registry CSV export.

**Confidence interpretation:** OCR confidence estimates how clearly Tesseract recognized text; it is not a certificate authenticity score. Field confidence estimates are based on matching extracted field tokens to Tesseract word-confidence output. If no field-token match is found, the page's OCR confidence is used as a fallback and should be treated as an estimate.

### Admin features

- Professional issuer dashboard
- Bulk PDF/image upload
- Automatic QR + OCR extraction
- Duplicate detection
- Extraction confidence
- Search by certificate ID, student, course or issuer
- Active / revoked status
- Re-activate revoked credentials
- Import batch history
- Import-item detail view
- Verification audit trail
- CSV registry export
- REST API
- PDF and image verification

### Normal user features

- Clean public verification page
- Upload PDF or image
- QR JSON and verification URL support
- OCR fallback/corroboration
- Clear verification result and score
- Field-level comparison
- Registry status display
- Mobile-responsive interface

## Important authenticity note

A local registry match proves that the uploaded certificate's extracted identity is consistent with a record stored in this application. It does **not**, by itself, prove that the issuer genuinely issued the certificate. For production use, connect the application to an issuer-controlled registry/API or a trusted signed credential mechanism.

## Requirements

- Windows 10/11
- Python 3.11+
- VS Code
- Tesseract OCR installed separately

Install Tesseract from a trusted Windows distribution and make sure `tesseract.exe` is on PATH. If it is not, configure `pytesseract.pytesseract.tesseract_cmd` in `app/services/ocr_service.py`.

## Setup on Windows

```powershell
cd EduCert_Verify
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python seed.py
python run.py
```

Open:

`http://127.0.0.1:5000`

## Admin login

Development defaults:

- Username: `admin`
- Password: `admin123`

Change these values in `.env` before deployment.

## Bulk import workflow

1. Open `http://127.0.0.1:5000/admin/login`.
2. Sign in.
3. In **Bulk certificate import**, select multiple PDFs/images.
4. Click **Import & Extract Automatically**.
5. Wait for the batch summary.
6. Imported credentials appear automatically in the registry.
7. Open the batch details for duplicates or files requiring review.
8. Use search/filter or CSV export as required.

No certificate-by-certificate form entry is required.

## Supported formats

- PDF
- PNG
- JPG / JPEG
- WEBP
- BMP

## QR support

The verifier supports both:

### JSON payloads

```json
{
  "certificate_id": "EDUSKILL-AWSGENAI-2026-001",
  "student_name": "Student Name",
  "course_name": "Course Name",
  "issuer": "EduSkills"
}
```

### Verification URLs

For example, EduSkills/Celonis-style QR values such as:

```text
https://certificate.eduskillsfoundation.org/verify/4f4ba85bc1adb22bb04f/4f4ba85bc1adb22bb04f
```

The application extracts the certificate ID from the verification URL.

## Test with the supplied Celonis certificate

The supplied certificate contains a QR verification URL. The extraction pipeline identifies:

- Certificate ID: `4f4ba85bc1adb22bb04f`
- Student name: `Akshay`
- Student ID: `STU69748ed416d031769246420`
- Course: `AI In Process Intelligence Virtual Internship` (OCR may vary slightly on the `AI` characters)
- Issuer: `Celonis / EduSkills`
- Period: `During June - August 2026`
- Verification URL: `https://certificate.eduskillsfoundation.org/verify/4f4ba85bc1adb22bb04f/4f4ba85bc1adb22bb04f`

The QR identifier is preferred over OCR when the two differ because OCR can confuse characters such as `1`, `l` and `I`.

## API

### Health

`GET /api/health`

### Verify

`POST /api/verify`

Multipart field:

`certificate=<PDF or image>`

### Certificate lookup

`GET /api/certificates/<certificate_id>`

## Project structure

```text
EduCert_Verify/
├── app/
│   ├── services/
│   │   ├── document_service.py
│   │   ├── import_service.py
│   │   ├── ocr_service.py
│   │   ├── qr_service.py
│   │   └── verifier.py
│   ├── static/css/style.css
│   ├── templates/
│   │   ├── admin.html
│   │   ├── admin_login.html
│   │   ├── base.html
│   │   ├── import_details.html
│   │   ├── index.html
│   │   └── result.html
│   ├── extensions.py
│   ├── models.py
│   ├── routes.py
│   └── __init__.py
├── data/uploads/
├── sample_certificates/
├── postman/
├── docs/
├── tests/
├── .env.example
├── requirements.txt
├── seed.py
├── run.py
└── README.md
```

## Change Log

### v2.0.0 — Automated Registry & Professional UI

- Replaced manual admin certificate entry with bulk certificate ingestion.
- Added QR + OCR automatic extraction service.
- Added duplicate detection.
- Added import batches and item-level audit records.
- Added extraction confidence.
- Added search and status filters.
- Added revoke / activate controls.
- Added CSV export.
- Added professional public verification UI.
- Added professional admin dashboard UI.
- Added responsive layouts.
- Added automatic migration for the new SQLite columns in older demo databases.

### v1.0.0

- Initial Flask project
- QR scanning
- OCR service
- Registry and verification engine
- Admin dashboard
- REST API
- Sample certificate
- Postman collection
- Report

## Persistence and history

EduCert Verify stores certificates, bulk-import batches, import items, verification logs, hashes, extracted fields and statuses in the database. The default local database is `data/educert.db`, using an absolute project-based path, so restarting `run.py` does not erase history.

For production or Vercel/serverless hosting, do not rely on SQLite or local `data/uploads` as permanent storage. Set `DATABASE_URL` to a managed PostgreSQL database (for example Supabase/Postgres) and mount or configure durable object storage for original certificate files. The registry data itself remains in PostgreSQL across restarts and redeployments.

Existing certificates can be corrected with **Re-extract** in the Admin Console when the original uploaded file is still available. Re-extraction never deletes the certificate record or its import/audit history.

### Extraction fields

The current extractor treats **Recipient Name** and **College / Institution** as separate fields. It does not use a generic `name` pattern, which previously could capture unrelated text. For the supplied Celonis/EduSkills certificate, the expected values are `Akshay` and `Srinivas Institute of Technology`.


## Review Queue

Certificates that cannot be safely registered automatically (especially when no reliable certificate ID can be extracted) are placed in the Admin **Review Queue**. Review does not mean fake. An administrator can re-extract, approve & register when a certificate ID is available, or dismiss the item. Review items retain their original uploaded file path and extracted JSON.

## Clean database

The distributed ZIP is shipped with an empty local registry/history. To clear local data again:

```powershell
python reset_data.py
```

The script prints the exact database and upload directory it will affect, shows record counts, and asks you to type `RESET` before deleting anything. This helps catch cases where the app is using a different `DATABASE_URL` or `UPLOAD_DIR` than expected. It clears certificates, review items, import batches and verification logs, and removes files inside the configured upload directory. It does not delete the database file itself.
