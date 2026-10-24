# Project1_Subject — Football Booking & Matchmaking

Project 1: football pitch bookings, team matchmaking, payment, ratings and admin dashboard.

## Stack from the project report
- Frontend: React + Vite + TypeScript; Tailwind CSS, shadcn/ui, Lucide; TanStack Query, Zustand, Recharts.
- Backend: Python Flask, SQLAlchemy, Flask-Migrate, Flask-JWT-Extended, Passlib/bcrypt, Google OAuth, Flask-SocketIO, VNPay/MoMo integrations, Celery + Redis, Pandas/OpenPyXL, Firebase Admin SDK.
- Database: existing 12-table TiDB Cloud schema, database `test`.

## Folder map
- `frontend/`: user and admin web application, features by business module.
- `backend/app/api/`: API routes; `models/`: ORM; `services/`: business logic; `integrations/`: third-party providers.
- `backend/app/tasks/`: background tasks; `realtime/`: websocket events; `reports/`: Excel exports.
- `database/`: DDL, demo seed and useful queries (do not rerun schema against populated cloud DB).
- `docs/`: architecture diagrams, API contracts, setup notes and course report.

## Important
This archive provides **folders and documentation placeholders only**, not a runnable web application.
If the GitHub repository already contains `backend/`, merge folders **without overwriting existing code**.
Never commit `.env`, credentials, database password or private service-account files.
Use a feature branch and open a pull request before merging into `main`.
The live database has already been provisioned; do not automatically run `CREATE TABLE` or migrations.
