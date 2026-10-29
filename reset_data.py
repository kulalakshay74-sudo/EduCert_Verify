"""Permanently clear registry, review queue, import history and verification history for local development."""
from pathlib import Path
import shutil
from app import create_app
from app.extensions import db
from app.models import Certificate, ImportBatch, ImportItem, VerificationLog

app = create_app()
with app.app_context():
    VerificationLog.query.delete()
    ImportItem.query.delete()
    ImportBatch.query.delete()
    Certificate.query.delete()
    db.session.commit()
    upload_dir = Path(app.config["UPLOAD_DIR"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    for child in upload_dir.iterdir():
        if child.is_file() or child.is_symlink(): child.unlink()
        elif child.is_dir(): shutil.rmtree(child)
    print("All certificate data, review items, import history and verification history were cleared.")
