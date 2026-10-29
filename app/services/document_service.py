from pathlib import Path
import tempfile


def get_image_paths(file_path):
    """Return one or more image paths for an image/PDF certificate.
    For PDFs, render every page to PNG using PyMuPDF.
    """
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        return [path]

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF support requires PyMuPDF. Install dependencies from requirements.txt.") from exc

    output_dir = Path(tempfile.mkdtemp(prefix="educert_pdf_"))
    doc = fitz.open(path)
    paths = []
    try:
        for index, page in enumerate(doc):
            # 2x rendering gives QR/OCR a better source image.
            pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
            out = output_dir / f"page_{index + 1}.png"
            pix.save(out)
            paths.append(out)
    finally:
        doc.close()
    return paths
