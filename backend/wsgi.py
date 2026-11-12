"""Production entry point: gunicorn wsgi:app --bind 0.0.0.0:$PORT"""
from app import create_app

app = create_app()
