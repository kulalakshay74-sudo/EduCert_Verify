import os
from pathlib import Path
from flask import Flask
from .extensions import db

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _ensure_schema(app):
    from sqlalchemy import inspect, text
    db.create_all()
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        tables = set(inspect(db.engine).get_table_names())
        if "certificate" not in tables:
            return
        existing = {c["name"] for c in inspect(db.engine).get_columns("certificate")}
        additions = {
            "student_id": "VARCHAR(120)", "recipient_name": "VARCHAR(200)", "institution_name": "VARCHAR(300)",
            "source_filename": "VARCHAR(300)", "source_path": "VARCHAR(700)", "extraction_method": "VARCHAR(80)",
            "extraction_confidence": "FLOAT", "ocr_confidence": "FLOAT DEFAULT 0", "extraction_version": "VARCHAR(30)", "raw_ocr": "TEXT",
            "source_file_hash": "VARCHAR(64)", "updated_at": "DATETIME",
        }
        with db.engine.begin() as conn:
            for name, typ in additions.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE certificate ADD COLUMN {name} {typ}"))
            if "import_item" in tables:
                item_columns = {c["name"] for c in inspect(db.engine).get_columns("import_item")}
                if "source_path" not in item_columns:
                    conn.execute(text("ALTER TABLE import_item ADD COLUMN source_path VARCHAR(700)"))
            if "recipient_name" in {c["name"] for c in inspect(db.engine).get_columns("certificate")}:
                conn.execute(text("UPDATE certificate SET recipient_name = student_name WHERE recipient_name IS NULL OR recipient_name = ''"))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    default_db = f"sqlite:///{(DATA_DIR / 'educert.db').as_posix()}"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", default_db)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
    app.config["MAX_BULK_FILES"] = int(os.getenv("MAX_BULK_FILES", "100"))
    app.config["DATA_DIR"] = DATA_DIR
    app.config["UPLOAD_DIR"] = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads")))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)


    @app.template_filter("fromjson")
    def fromjson_filter(value):
        import json
        try:
            return json.loads(value or "{}")
        except Exception:
            return {}
    db.init_app(app)
    from .routes import web, api
    app.register_blueprint(web)
    app.register_blueprint(api, url_prefix="/api")
    with app.app_context():
        _ensure_schema(app)
    return app
