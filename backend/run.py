"""Local development server. On the cloud use a WSGI server instead: gunicorn wsgi:app (see Procfile)."""
import os
from app import create_app

if __name__ == '__main__':
    create_app().run(host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '5000')), debug=False)
