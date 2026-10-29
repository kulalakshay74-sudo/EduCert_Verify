"""Clear local EduCert registry, review/import history, verification history and uploaded files.

Run explicitly with: python reset_data.py
This operation is destructive. It does not delete the database file itself.
"""
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import Certificate, ImportBatch, ImportItem, VerificationLog


def main():
    app = create_app()

    with app.app_context():
        database_url = db.engine.url.render_as_string(hide_password=True)
        upload_dir = Path(app.config["UPLOAD_DIR"]).resolve()
        models = (
            ("certificates", Certificate),
            ("import batches", ImportBatch),
            ("import items / review queue", ImportItem),
            ("verification logs", VerificationLog),
        )

        print("\nEduCert Verify — destructive data reset")
        print(f"Database:   {database_url}")
        print(f"Upload dir: {upload_dir}")
        print("\nCurrent records:")
        for label, model in models:
            print(f"  {label}: {model.query.count()}")

        answer = input(
            "\nThis permanently deletes the records above and all files inside "
            f"'{upload_dir}'. Type RESET to continue: "
        ).strip()

        if answer != "RESET":
            print("Cancelled. No records or files were deleted.")
            return

        # Remove child/audit rows before parent records.
        VerificationLog.query.delete(synchronize_session=False)
        ImportItem.query.delete(synchronize_session=False)
        ImportBatch.query.delete(synchronize_session=False)
        Certificate.query.delete(synchronize_session=False)
        db.session.commit()

        upload_dir.mkdir(parents=True, exist_ok=True)
        for child in upload_dir.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                import shutil
                shutil.rmtree(child)

        print("\nReset completed.")
        print(f"Database:   {database_url}")
        print(f"Upload dir: {upload_dir}")
        print("Remaining records:")
        for label, model in models:
            print(f"  {label}: {model.query.count()}")


if __name__ == "__main__":
    main()
