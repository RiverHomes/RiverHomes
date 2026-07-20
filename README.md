# Murima Ledger PWA

A distinct, branded receipt-and-messages demo with:
- registration before private access,
- a per-user receipt view,
- a one-way messages app,
- admin approval and editing,
- referral tracking,
- download activity logs,
- offline PWA shell support.

## Run locally
```bash
pip install -r requirements.txt
python app.py
```

## Render
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app`

Set optional env vars:
- `ADMIN_ROUTE` (optional; otherwise the route is stored in the admin database)
- `ADMIN_USERNAME` (defaults to `admin`)
- `ADMIN_PASSWORD` (if set, this becomes the admin password and is synced into the admin database)
- `SECRET_KEY`
- `SECRET_SALT`
- `APP_NAME`

If `ADMIN_PASSWORD` is set on Render, the app will create or update that admin account automatically at startup, and the login form will use those credentials instead of a one-time registration flow.
