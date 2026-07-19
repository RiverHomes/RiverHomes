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
- `SECRET_KEY`
- `SECRET_SALT`
- `APP_NAME`

Admin accounts now use a username + password hash stored in the database, and the admin route is loaded from the admin database or the `ADMIN_ROUTE` environment variable.
