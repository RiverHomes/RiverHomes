# River Homes

A clean, role-gated marketplace for Kenyan rental homes, business spaces, real estate, vehicles and online listings.

## Local run
```bash
python -m venv venv
venv\Scriptsctivate   # Windows
pip install -r requirements.txt
python app.py
```

## Main flow
- `/` opens the tenant / landlord choice screen.
- `/hub` appears only after a role is selected.
- `/buh` is the private admin console.
- `/qr` shows a printable QR code.

## Render notes
- Start command: `gunicorn app:app`
- Build command: `pip install -r requirements.txt`
- Set `SITE_URL` after deploy so the QR code points at the live domain.
- For production image persistence, attach external storage or a persistent disk.
