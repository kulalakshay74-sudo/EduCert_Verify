"""Initialize an empty EduCert Verify database. No sample certificates are inserted."""
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    db.create_all()
    print("EduCert Verify database initialized. No seed certificates were added.")
