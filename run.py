import os
from src import create_app, db

# Determine environment from .env, default to development
env = os.getenv("FLASK_ENV", "development")

app = create_app(env)

if __name__ == "__main__":
    # This block is only run when you execute `python run.py` locally
    # It is NOT used by Gunicorn
    
    # In development, we can auto-create tables
    with app.app_context():
        # WARNING: In production, use Alembic Migrations instead of create_all()
        # But for this setup phase, this ensures the DB exists
        db.create_all()
        print("Database tables verified.")

    app.run(host="0.0.0.0", port=8000)