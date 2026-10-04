"""Entry point for Render: initialize the selected database before Gunicorn starts."""

from app import app, init_db

# With Gunicorn --preload this runs once in the master process, before workers
# fork. init_db() chooses PostgreSQL whenever DATABASE_URL is set; local
# `python app.py` keeps using the existing SQLite startup path.
init_db()
