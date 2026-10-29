from pathlib import Path
import os
import tempfile


def get_image_paths(file_path):
    """Return image paths; render PDFs at OCR-friendly resolution and cap scanned pages."""
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        return [path]

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF support requires PyMuPDF. Install dependencies from requirements.txt.") from exc

    try:
        max_pages = max(1, int(os.getenv("EDUCERT_OCR_MAX_PAGES", "3")))
    except ValueError:
        max_pages = 3

    output_dir = Path(tempfile.mkdtemp(prefix="educert_pdf_"))
    paths = []
    with fitz.open(path) as doc:
        page_count = min(len(doc), max_pages)
        for index in range(page_count):
            page = doc.load_page(index)
            # 2x is sufficient for typical certificate text and is far faster/smaller than 4x.
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            out = output_dir / f"page_{index + 1}.png"
            pix.save(out)
            paths.append(out)
    return paths
