import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "site.db"
ADMIN_DB_PATH = BASE_DIR / "admin.db"
APP_NAME = os.getenv("APP_NAME", "Murima Ledger")
SECRET_SALT = os.getenv("SECRET_SALT", "change-me-in-production")
COOKIE_MAX_AGE = 60 * 60 * 24 * 365
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
def db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db
@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
def admin_db():
    conn = sqlite3.connect(ADMIN_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def _ensure_admin_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
def load_admin_route() -> str:
    # Keep the admin entry point out of the normal navigation and always
    # serve the same private route unless ADMIN_ROUTE is explicitly set.
    default_route = "xtspolsjhulupjoppsup****lmkzcodup"
    env_route = (os.getenv("ADMIN_ROUTE") or "").strip().strip("/")
    route = env_route or default_route
    conn = sqlite3.connect(ADMIN_DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        _ensure_admin_meta_table(conn)
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('admin_route', ?)",
            (route,),
        )
        conn.commit()
        return route
    finally:
        conn.close()
ADMIN_ROUTE = load_admin_route()
def ensure_column(cur, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
def init_admin_db():
    conn = sqlite3.connect(ADMIN_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    _ensure_admin_meta_table(conn)
    existing_cols = [row["name"] for row in cur.execute("PRAGMA table_info(admins)").fetchall()]
    if existing_cols and "username" not in existing_cols:
        cur.execute("DROP TABLE IF EXISTS admins")
        existing_cols = []
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
def admin_password_hash(password: str) -> str:
    return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
def admin_cookie_token(username: str, password_hash_value: str) -> str:
    return hashlib.sha256(f"{username}:{password_hash_value}:{SECRET_SALT}".encode()).hexdigest()
def admin_rows():
    conn = admin_db()
    rows = conn.execute("SELECT * FROM admins ORDER BY id ASC").fetchall()
    conn.close()
    return rows
def first_admin_username() -> str:
    rows = admin_rows()
    return rows[0]["username"] if rows else ""
def is_admin_username(username: str) -> bool:
    if not username:
        return False
    conn = admin_db()
    row = conn.execute("SELECT 1 FROM admins WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row is not None
def first_admin_count() -> int:
    conn = admin_db()
    count = conn.execute("SELECT COUNT(*) AS c FROM admins").fetchone()["c"]
    conn.close()
    return count
def promote_admin(username: str, password: str = "") -> bool:
    username = (username or "").strip()
    if not username:
        return False
    password_hash_value = admin_password_hash(password) if password else ""
    conn = admin_db()
    try:
        existing = conn.execute("SELECT id FROM admins WHERE username = ?", (username,)).fetchone()
        if existing:
            if password:
                conn.execute(
                    "UPDATE admins SET password_hash = ? WHERE username = ?",
                    (password_hash_value, username),
                )
        else:
            conn.execute(
                "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash_value, now_iso()),
            )
        conn.commit()
    finally:
        conn.close()
    return True
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_key TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            contact TEXT NOT NULL,
            contact_masked TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 100.0,
            transaction_cost REAL NOT NULL DEFAULT 0.0,
            receipt_time TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0.0,
            code TEXT NOT NULL,
            receipt_note TEXT DEFAULT '',
            recipient_name TEXT NOT NULL DEFAULT '',
            referrer_public_key TEXT NOT NULL DEFAULT '',
            approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    ensure_column(cur, "users", "referrer_public_key", "TEXT NOT NULL DEFAULT ''")
    ensure_column(cur, "users", "recipient_name", "TEXT NOT NULL DEFAULT ''")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_public_key TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_public_key) REFERENCES users(public_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS download_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_public_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            amount REAL NOT NULL,
            referrer_public_key TEXT NOT NULL DEFAULT '',
            ip_address TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            site_name TEXT NOT NULL,
            brand_subtitle TEXT NOT NULL,
            receipt_heading TEXT NOT NULL,
            receipt_subheading TEXT NOT NULL,
            message_heading TEXT NOT NULL,
            footer_note TEXT NOT NULL,
            download_link TEXT NOT NULL
        )
        """
    )
    conn.commit()
    cur.execute("SELECT COUNT(*) AS c FROM admin_settings")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            """
            INSERT INTO admin_settings
            (id, site_name, brand_subtitle, receipt_heading, receipt_subheading, message_heading, footer_note, download_link)
            VALUES
            (1, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                APP_NAME,
                "Personal transaction studio",
                "Transaction complete",
                "A private receipt experience for your registered users.",
                "Messages",
                "Custom notifications and announcements appear here.",
                "https://dad.cx/TJ",
            ),
        )
        conn.commit()
    conn.close()
def get_settings():
    return db().execute("SELECT * FROM admin_settings WHERE id = 1").fetchone()
@app.context_processor
def inject_globals():
    return {
        "app_name": APP_NAME,
        "admin_route": ADMIN_ROUTE,
        "settings": get_settings(),
    }
def normalize_phone(value: str) -> str:
    return re.sub(r"\D+", "", value or "")
def mask_contact(value: str) -> str:
    digits = normalize_phone(value)
    if len(digits) >= 7:
        return f"{digits[:4]}***{digits[-3:]}"
    if digits:
        return f"{digits[:4]}***"
    return "***"
def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")
def parse_datetime_input(value: str) -> str:
    if not value:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    try:
        dt_obj = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        return dt_obj.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value.replace("T", " ")[:16]
def safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
def build_code(display_name: str, contact: str, receipt_time: str) -> str:
    payload = f"{display_name}|{contact}|{receipt_time}|{SECRET_SALT}".encode()
    digest = hashlib.sha256(payload).hexdigest().upper()
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    compact = []
    for i in range(0, 16, 2):
        n = int(digest[i : i + 2], 16)
        compact.append(alphabet[n % len(alphabet)])
    tail = digest[-4:]
    return f"{''.join(compact[:3])}-{''.join(compact[3:6])}-{tail}"
def create_public_key(display_name: str, contact: str, receipt_time: str) -> str:
    payload = f"{display_name}|{contact}|{receipt_time}|{uuid.uuid4()}|{SECRET_SALT}".encode()
    digest = hashlib.sha256(payload).hexdigest().upper()
    return f"MUR-{digest[:10]}"
def receipt_payload(user):
    return {
        "display_name": user["display_name"],
        "contact": user["contact"],
        "contact_masked": user["contact_masked"],
        "recipient_name": user["recipient_name"] or user["display_name"],
        "amount": float(user["amount"] or 0.0),
        "transaction_cost": float(user["transaction_cost"] or 0.0),
        "receipt_time": user["receipt_time"],
        "code": user["code"],
        "receipt_note": user["receipt_note"] or "",
    }
def _load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            if os.path.exists(candidate):
                return ImageFont.truetype(candidate, size=size)
        except Exception:
            pass
    return ImageFont.load_default()
def render_receipt_png(user):
    data = receipt_payload(user)
    img = Image.new("RGB", (1400, 1800), "#101216")
    draw = ImageDraw.Draw(img)
    card = (80, 90, 1320, 1710)
    draw.rounded_rectangle(card, radius=48, fill="#191c22")
    for x in range(card[0], card[2]):
        t = (x - card[0]) / (card[2] - card[0])
        r = int(41 + (45 - 41) * t)
        g = int(151 + (216 - 151) * t)
        b = int(255 - (255 - 111) * t)
        draw.line((x, 92, x, 95), fill=(r, g, b))
    draw.ellipse((610, 150, 790, 330), fill="#12151b", outline="#2a2f39", width=4)
    draw.text((700, 225), "🎉", font=_load_font(86), fill="#ffffff", anchor="mm")
    f_title = _load_font(56, True)
    f_small = _load_font(30, False)
    f_big = _load_font(86, True)
    f_mid = _load_font(34, False)
    f_mid_b = _load_font(34, True)
    draw.multiline_text((700, 395), "Your transaction\nwas successful", font=f_title, fill="#ffffff", anchor="ma", align="center", spacing=6)
    draw.text((700, 560), data["receipt_time"], font=f_small, fill="#b8bfca", anchor="ma")
    draw.text((700, 670), f"Ksh {data['amount']:.2f}", font=f_big, fill="#ffffff", anchor="ma")
    draw.text((700, 790), f"Transaction cost: Ksh {data['transaction_cost']:.2f}", font=f_mid, fill="#b8bfca", anchor="ma")
    draw.text((520, 880), "ID:", font=f_mid_b, fill="#30e06f")
    draw.text((585, 880), data["code"], font=f_mid_b, fill="#30e06f")
    draw.text((1060, 880), "⧉ Copy", font=f_mid_b, fill="#30e06f")
    draw.rounded_rectangle((170, 980, 1230, 1225), radius=28, fill="#232831")
    draw.text((210, 1020), "Send to:", font=f_small, fill="#c2c8d2")
    draw.ellipse((225, 1075, 340, 1190), fill="#8b4f22")
    initials = (data["display_name"][:2] or "??").upper()
    draw.text((283, 1132), initials, font=_load_font(40, True), fill="#ffb26f", anchor="mm")
    draw.text((380, 1088), data["recipient_name"], font=f_mid_b, fill="#ffffff")
    draw.text((380, 1140), data["contact_masked"], font=f_mid, fill="#c7ced8")
    if data["receipt_note"]:
        draw.rounded_rectangle((170, 1260, 1230, 1370), radius=24, fill="#232831")
        draw.text((210, 1300), data["receipt_note"], font=f_mid, fill="#d9dee7")
    # Bottom row: four evenly spaced actions plus Done.
    btn_y0, btn_y1 = 1418, 1560
    left_pad, right_pad, gap = 140, 140, 22
    usable = 1400 - left_pad - right_pad - gap * 3
    btn_w = usable // 4
    boxes = []
    x = left_pad
    for _ in range(4):
        boxes.append((x, btn_y0, x + btn_w, btn_y1))
        x += btn_w + gap
    done_btn = (280, 1600, 1120, 1678)
    for box in boxes:
        draw.rounded_rectangle(box, radius=26, fill="#20242d")
    centers = [int((b[0] + b[2]) / 2) for b in boxes]
    icon_y = 1488
    text_y = 1528
    # Add to favourites icon (outlined star)
    cx = centers[0]
    draw.ellipse((cx - 29, icon_y - 29, cx + 29, icon_y + 29), fill="#2a2e36")
    star = [(cx, 1453), (cx + 7, 1466), (cx + 23, 1468), (cx + 11, 1478), (cx + 15, 1494), (cx, 1486), (cx - 15, 1494), (cx - 11, 1478), (cx - 23, 1468), (cx - 7, 1466)]
    draw.line(star + [star[0]], fill="#30e06f", width=4, joint="curve")
    draw.multiline_text((cx, text_y), "Add to\nfavourites", font=f_small, fill="#ffffff", anchor="ma", align="center", spacing=4)
    # Reverse transaction icon (counter-clockwise arrow)
    cx = centers[1]
    draw.ellipse((cx - 29, icon_y - 29, cx + 29, icon_y + 29), fill="#2a2e36")
    draw.arc((cx - 18, icon_y - 18, cx + 18, icon_y + 18), start=35, end=325, fill="#30e06f", width=4)
    draw.polygon([(cx - 11, icon_y - 16), (cx - 23, icon_y - 13), (cx - 16, icon_y - 4)], fill="#30e06f")
    draw.multiline_text((cx, text_y), "Reverse\ntransaction", font=f_small, fill="#ffffff", anchor="ma", align="center", spacing=4)
    # Download receipt icon (document outline + red bar)
    cx = centers[2]
    draw.ellipse((cx - 29, icon_y - 29, cx + 29, icon_y + 29), fill="#2a2e36")
    draw.polygon([(cx - 12, icon_y - 17), (cx + 6, icon_y - 17), (cx + 14, icon_y - 9), (cx + 14, icon_y + 19), (cx - 12, icon_y + 19)], outline="#30e06f", fill=None)
    draw.line((cx + 6, icon_y - 17, cx + 6, icon_y - 9, cx + 14, icon_y - 9), fill="#30e06f", width=3)
    draw.rounded_rectangle((cx - 14, icon_y - 2, cx + 14, icon_y + 4), radius=2, fill="#e74b5a")
    draw.multiline_text((cx, text_y), "Download\nreceipt", font=f_small, fill="#ffffff", anchor="ma", align="center", spacing=4)
    # Share details icon (upload/share arrow)
    cx = centers[3]
    draw.ellipse((cx - 29, icon_y - 29, cx + 29, icon_y + 29), fill="#2a2e36")
    draw.line((cx, icon_y + 14, cx, icon_y - 10), fill="#30e06f", width=4)
    draw.polygon([(cx - 8, icon_y - 3), (cx, icon_y - 15), (cx + 8, icon_y - 3)], outline="#ff7a45", fill=None)
    draw.line((cx - 14, icon_y + 14, cx + 14, icon_y + 14), fill="#30e06f", width=4)
    draw.multiline_text((cx, text_y), "Share\ndetails", font=f_small, fill="#ffffff", anchor="ma", align="center", spacing=4)
    draw.rounded_rectangle(done_btn, radius=24, fill="#2dd86f")
    draw.text((700, 1638), "Done", font=_load_font(36, True), fill="#ffffff", anchor="ma")
    return img

def render_receipt_pdf(user):
    data = receipt_payload(user)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFillColor(HexColor("#101216"))
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.setFillColor(HexColor("#191c22"))
    c.roundRect(36, 36, w - 72, h - 72, 26, fill=1, stroke=0)
    c.setStrokeColor(HexColor("#2dd86f"))
    c.line(36, h - 40, w - 36, h - 40)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w / 2, h - 120, "Your transaction was")
    c.drawCentredString(w / 2, h - 150, "Successful")
    c.setFillColor(HexColor("#b8bfca"))
    c.setFont("Helvetica", 12)
    c.drawCentredString(w / 2, h - 188, data["receipt_time"])
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(w / 2, h - 240, f"Ksh {data['amount']:.2f}")
    c.setFont("Helvetica", 12)
    c.setFillColor(HexColor("#b8bfca"))
    c.drawCentredString(w / 2, h - 266, f"Transaction cost: Ksh {data['transaction_cost']:.2f}")
    c.setFillColor(HexColor("#30e06f"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(80, h - 300, f"ID: {data['code']}")
    c.drawRightString(w - 80, h - 300, "Copy")
    c.setFillColor(HexColor("#c7ced8"))
    c.setFont("Helvetica", 12)
    c.drawString(80, h - 360, f"Send to: {data['recipient_name']}")
    c.drawString(80, h - 382, f"Contact: {data['contact_masked']}")
    if data["receipt_note"]:
        text_obj = c.beginText(80, h - 430)
        text_obj.setFont("Helvetica", 11)
        text_obj.setFillColor(HexColor("#d9dee7"))
        text_obj.textLines(data["receipt_note"])
        c.drawText(text_obj)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf
def current_user_key():
    return request.args.get("key") or request.form.get("key") or request.cookies.get("user_key")
def fetch_user(public_key: str):
    if not public_key:
        return None
    return db().execute("SELECT * FROM users WHERE public_key = ?", (public_key,)).fetchone()
def seed_default_messages(public_key: str) -> None:
    user = fetch_user(public_key)
    if not user:
        return
    conn = db()
    existing = conn.execute(
        "SELECT COUNT(*) AS c FROM messages WHERE user_public_key = ?",
        (public_key,),
    ).fetchone()["c"]
    if existing:
        return
    now = now_iso()
    defaults = [
        ("System", "Your account is now under review. Please wait for admin approval before generating the receipt."),
        ("Support", "Approval received. You can now complete your receipt details from your private page."),
        ("Payments Desk", "Transaction draft created successfully. Final receipt will appear after you save the details."),
        ("Notifications", "This inbox is one-way only. Replies are disabled to keep it clean and read-only."),
        ("Ledger Update", "All five sample messages are ready and will stay in the inbox until you remove them from the admin dashboard."),
    ]
    for sender_name, body in defaults:
        conn.execute(
            "INSERT INTO messages (user_public_key, sender_name, body, created_at, pinned) VALUES (?, ?, ?, ?, 0)",
            (public_key, sender_name, body, now),
        )
    conn.commit()
def admin_is_authenticated() -> bool:
    token = request.cookies.get("admin_auth") or ""
    if not token:
        return False
    for row in admin_rows():
        if hmac.compare_digest(token, admin_cookie_token(row["username"], row["password_hash"])):
            return True
    return False
def require_admin(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not admin_is_authenticated():
            flash("Please log in again.", "error")
            return redirect(url_for("admin_entry"))
        return view(*args, **kwargs)
    return wrapper
def require_registered_user(view):
    @wraps(view)
    def wrapper(public_key, *args, **kwargs):
        user = fetch_user(public_key)
        if not user:
            abort(404)
        cookie_key = request.cookies.get("user_key")
        if cookie_key != public_key:
            flash("Please register first to access your page.", "error")
            return redirect(url_for("index"))
        return view(public_key, *args, **kwargs)
    return wrapper
@app.route("/service-worker.js")
def service_worker():
    response = make_response(send_from_directory(BASE_DIR / "static", "service-worker.js"))
    response.headers["Content-Type"] = "application/javascript"
    return response
@app.route("/")
def index():
    key = current_user_key()
    user = fetch_user(key)
    if user:
        if user["approved"]:
            return redirect(url_for("user_home", public_key=user["public_key"]))
        return render_template("public_approval.html", user=user, settings=get_settings())
    ref_key = (request.args.get("ref") or "").strip()
    referral = fetch_user(ref_key) if ref_key else None
    return render_template("auth.html", referral=referral, settings=get_settings())
@app.route("/register", methods=["POST"])
def register():
    display_name = (request.form.get("display_name") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    amount = 0.0
    receipt_time = parse_datetime_input(request.form.get("receipt_time") or "")
    receipt_note = (request.form.get("receipt_note") or "").strip()
    referrer_public_key = (request.form.get("referrer_public_key") or request.args.get("ref") or "").strip()
    if not display_name or not contact:
        flash("Please enter a name and contact.", "error")
        return redirect(url_for("index"))
    if referrer_public_key and not fetch_user(referrer_public_key):
        referrer_public_key = ""
    contact_masked = mask_contact(contact)
    public_key = create_public_key(display_name, contact, receipt_time)
    code = build_code(display_name, contact, receipt_time)
    balance = 0.0
    conn = db()
    conn.execute(
        """
        INSERT INTO users
        (public_key, display_name, contact, contact_masked, amount, transaction_cost, receipt_time, balance, code, receipt_note, recipient_name, referrer_public_key, approved, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            public_key,
            display_name,
            contact,
            contact_masked,
            amount,
            0.0,
            receipt_time,
            balance,
            code,
            receipt_note,
            "",
            referrer_public_key,
            now_iso(),
            now_iso(),
        ),
    )
    conn.commit()
    if first_admin_count() == 0:
        promote_admin(public_key)
    response = redirect(url_for("user_home", public_key=public_key))
    response.set_cookie("user_key", public_key, max_age=COOKIE_MAX_AGE, samesite="Lax", path="/")
    flash("Registration saved. It is now waiting for admin approval.", "success")
    return response
@app.route("/login", methods=["POST"])
def login_user():
    display_name = (request.form.get("display_name") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    if not display_name or not contact:
        flash("Enter your name and contact to log in.", "error")
        return redirect(url_for("index"))
    normalized_contact = normalize_phone(contact)
    candidates = db().execute(
        "SELECT * FROM users WHERE lower(display_name) = lower(?)",
        (display_name,),
    ).fetchall()
    user = None
    for row in candidates:
        if normalize_phone(row["contact"]) == normalized_contact:
            user = row
            break
    if not user:
        flash("No matching account was found.", "error")
        return redirect(url_for("index"))
    response = redirect(url_for("user_home", public_key=user["public_key"]))
    response.set_cookie("user_key", user["public_key"], max_age=COOKIE_MAX_AGE, samesite="Lax", path="/")
    flash("Welcome back.", "success")
    return response
@app.route("/u/<public_key>")
@require_registered_user
def user_home(public_key):
    user = fetch_user(public_key)
    if not user:
        abort(404)
    if not user["approved"]:
        return render_template("public_approval.html", user=user, settings=get_settings())
    seed_default_messages(public_key)
    user = fetch_user(public_key)
    messages = db().execute(
        "SELECT * FROM messages WHERE user_public_key = ? ORDER BY pinned DESC, id DESC",
        (public_key,),
    ).fetchall()
    download_count = db().execute(
        "SELECT COUNT(*) AS c FROM download_logs WHERE user_public_key = ?",
        (public_key,),
    ).fetchone()["c"]
    referral_count = db().execute(
        "SELECT COUNT(*) AS c FROM users WHERE referrer_public_key = ?",
        (public_key,),
    ).fetchone()["c"]
    return render_template(
        "receipt.html",
        user=user,
        messages=messages,
        settings=get_settings(),
        printable=False,
        download_count=download_count,
        referral_count=referral_count,
        editable=True,
        no_chrome=True,
    )
@app.route("/u/<public_key>/messages")
@require_registered_user
def user_messages(public_key):
    user = fetch_user(public_key)
    if not user:
        abort(404)
    if not user["approved"]:
        return render_template("public_approval.html", user=user, settings=get_settings())
    messages = db().execute(
        "SELECT * FROM messages WHERE user_public_key = ? ORDER BY pinned DESC, id DESC",
        (public_key,),
    ).fetchall()
    return render_template("messages.html", user=user, messages=messages, settings=get_settings())
@app.route("/u/<public_key>/receipt", methods=["POST"])
@require_registered_user
def save_receipt(public_key):
    user = fetch_user(public_key)
    if not user:
        abort(404)
    if not user["approved"]:
        return render_template("public_approval.html", user=user, settings=get_settings())
    amount = safe_float(request.form.get("amount"), float(user["amount"]))
    recipient_name = (request.form.get("recipient_name") or user["recipient_name"] or user["display_name"]).strip()
    receipt_time = parse_datetime_input(request.form.get("receipt_time") or user["receipt_time"])
    receipt_note = (request.form.get("receipt_note") or "").strip()
    contact = (request.form.get("contact") or user["contact"]).strip()
    contact_masked = mask_contact(contact)
    code = build_code(user["display_name"], contact, receipt_time)
    balance = 0.0
    db().execute(
        """
        UPDATE users
        SET contact = ?, contact_masked = ?, amount = ?, receipt_time = ?, balance = ?, code = ?, receipt_note = ?, recipient_name = ?, updated_at = ?
        WHERE public_key = ?
        """,
        (contact, contact_masked, amount, receipt_time, balance, code, receipt_note, recipient_name, now_iso(), public_key),
    )
    db().commit()
    seed_default_messages(public_key)
    flash("Receipt details saved.", "success")
    return redirect(url_for("user_home", public_key=public_key))
@app.route("/u/<public_key>/download")
@require_registered_user
def download_receipt(public_key):
    return redirect(url_for("download_receipt_png", public_key=public_key))
@app.route("/u/<public_key>/download/png")
@require_registered_user
def download_receipt_png(public_key):
    user = fetch_user(public_key)
    if not user:
        abort(404)
    db().execute(
        """
        INSERT INTO download_logs
        (user_public_key, display_name, amount, referrer_public_key, ip_address, user_agent, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["public_key"],
            user["display_name"],
            user["amount"],
            user["referrer_public_key"],
            request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            request.headers.get("User-Agent", ""),
            now_iso(),
        ),
    )
    db().commit()
    img = render_receipt_png(user)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", as_attachment=True, download_name=f"receipt-{public_key}.png")
@app.route("/u/<public_key>/download/pdf")
@require_registered_user
def download_receipt_pdf(public_key):
    user = fetch_user(public_key)
    if not user:
        abort(404)
    db().execute(
        """
        INSERT INTO download_logs
        (user_public_key, display_name, amount, referrer_public_key, ip_address, user_agent, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["public_key"],
            user["display_name"],
            user["amount"],
            user["referrer_public_key"],
            request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            request.headers.get("User-Agent", ""),
            now_iso(),
        ),
    )
    db().commit()
    buf = render_receipt_pdf(user)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=f"receipt-{public_key}.pdf")
@app.route("/receipt-app")
def receipt_app():
    return render_template("receipt_app.html", settings=get_settings(), no_chrome=True)
@app.route("/sms-app")
def sms_app():
    return render_template("sms_app.html", settings=get_settings(), no_chrome=True)
@app.route(f"/{ADMIN_ROUTE}", methods=["GET", "POST"])
def admin_entry():
    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower() or "login"
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        if action == "register":
            if not username:
                flash("Choose an admin username.", "error")
                return redirect(url_for("admin_entry"))
            if not password:
                flash("Set an admin password.", "error")
                return redirect(url_for("admin_entry"))
            promote_admin(username, password=password)
            conn = admin_db()
            row = conn.execute("SELECT password_hash FROM admins WHERE username = ?", (username,)).fetchone()
            conn.close()
            stored_hash = row["password_hash"] if row else admin_password_hash(password)
            resp = redirect(url_for("admin_dashboard"))
            resp.set_cookie("admin_auth", admin_cookie_token(username, stored_hash), httponly=True, samesite="Lax", max_age=COOKIE_MAX_AGE, path="/")
            flash("Admin registered and signed in.", "success")
            return resp
        if not username or not password:
            flash("Enter admin username and password.", "error")
            return redirect(url_for("admin_entry"))
        conn = admin_db()
        row = conn.execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
        conn.close()
        if not row:
            flash("That admin username was not found.", "error")
            return redirect(url_for("admin_entry"))
        stored_hash = row["password_hash"] or ""
        if not stored_hash or not check_password_hash(stored_hash, password):
            flash("Incorrect admin password.", "error")
            return redirect(url_for("admin_entry"))
        resp = redirect(url_for("admin_dashboard"))
        resp.set_cookie("admin_auth", admin_cookie_token(username, stored_hash), httponly=True, samesite="Lax", max_age=COOKIE_MAX_AGE, path="/")
        flash("Welcome, admin.", "success")
        return resp
    if admin_is_authenticated():
        return redirect(url_for("admin_dashboard"))
    rows = admin_rows()
    mode = "register" if not rows else "login"
    return render_template(
        "admin_login.html",
        error=None,
        mode=mode,
        first_admin_username=first_admin_username(),
        admin_count=len(rows),
    )
@app.route(f"/{ADMIN_ROUTE}/dashboard", methods=["GET"])
@require_admin
def admin_dashboard():
    users = db().execute("SELECT * FROM users ORDER BY approved ASC, id DESC").fetchall()
    settings = get_settings()
    messages_by_user = {}
    conn_admin = admin_db()
    admin_rows = conn_admin.execute("SELECT username, created_at FROM admins ORDER BY id ASC").fetchall()
    conn_admin.close()
    referral_counts = {
        row["referrer_public_key"]: row["c"]
        for row in db().execute(
            "SELECT referrer_public_key, COUNT(*) AS c FROM users WHERE referrer_public_key != '' GROUP BY referrer_public_key"
        ).fetchall()
    }
    download_counts = {
        row["user_public_key"]: row["c"]
        for row in db().execute(
            "SELECT user_public_key, COUNT(*) AS c FROM download_logs GROUP BY user_public_key"
        ).fetchall()
    }
    for u in users:
        rows = db().execute(
            "SELECT * FROM messages WHERE user_public_key = ? ORDER BY pinned DESC, id DESC",
            (u["public_key"],),
        ).fetchall()
        messages_by_user[u["public_key"]] = rows
    download_logs = db().execute(
        "SELECT * FROM download_logs ORDER BY id DESC LIMIT 50"
    ).fetchall()
    return render_template(
        "admin_dashboard.html",
        users=users,
        settings=settings,
        messages_by_user=messages_by_user,
        referral_counts=referral_counts,
        download_counts=download_counts,
        download_logs=download_logs,
        admins=admin_rows,
    )
@app.route(f"/{ADMIN_ROUTE}/approve/<public_key>", methods=["POST"])
@require_admin
def approve_user(public_key):
    try:
        user = fetch_user(public_key)
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("admin_dashboard"))

        db().execute("UPDATE users SET approved = 1, updated_at = ? WHERE public_key = ?", (now_iso(), public_key))
        db().commit()
        try:
            seed_default_messages(public_key)
        except Exception:
            app.logger.exception("Failed to seed default messages for %s", public_key)
        flash("User approved.", "success")
    except Exception:
        app.logger.exception("Failed to approve user %s", public_key)
        flash("Could not approve the user. Please try again.", "error")
    return redirect(url_for("admin_dashboard"))
@app.route(f"/{ADMIN_ROUTE}/delete/<public_key>", methods=["POST"])
@require_admin
def delete_user(public_key):
    db().execute("DELETE FROM messages WHERE user_public_key = ?", (public_key,))
    db().execute("DELETE FROM download_logs WHERE user_public_key = ?", (public_key,))
    db().execute("DELETE FROM users WHERE public_key = ?", (public_key,))
    db().commit()
    flash("User removed.", "success")
    return redirect(url_for("admin_dashboard"))
@app.route(f"/{ADMIN_ROUTE}/admin/add", methods=["POST"])
@require_admin
def add_admin():
    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()
    if not username:
        flash("Enter an admin username.", "error")
        return redirect(url_for("admin_dashboard"))
    if not password:
        flash("Set a password for the new admin.", "error")
        return redirect(url_for("admin_dashboard"))
    promote_admin(username, password=password)
    flash("Admin added.", "success")
    return redirect(url_for("admin_dashboard"))
@app.route(f"/{ADMIN_ROUTE}/admin/remove/<username>", methods=["POST"])
@require_admin
def remove_admin(username):
    if first_admin_count() <= 1:
        flash("You need at least one admin.", "error")
        return redirect(url_for("admin_dashboard"))
    conn = admin_db()
    conn.execute("DELETE FROM admins WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    flash("Admin removed.", "success")
    return redirect(url_for("admin_dashboard"))
@app.route(f"/{ADMIN_ROUTE}/save/<public_key>", methods=["POST"])
@require_admin
def save_user(public_key):
    display_name = (request.form.get("display_name") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    amount = safe_float(request.form.get("amount"), 0.0)
    receipt_time = parse_datetime_input(request.form.get("receipt_time") or "")
    receipt_note = (request.form.get("receipt_note") or "").strip()
    contact_masked = mask_contact(contact)
    code = build_code(display_name, contact, receipt_time)
    balance = 0.0
    db().execute(
        """
        UPDATE users
        SET display_name = ?, contact = ?, contact_masked = ?, amount = ?, receipt_time = ?, balance = ?, code = ?, receipt_note = ?, updated_at = ?
        WHERE public_key = ?
        """,
        (
            display_name,
            contact,
            contact_masked,
            amount,
            receipt_time,
            balance,
            code,
            receipt_note,
            now_iso(),
            public_key,
        ),
    )
    db().commit()
    flash("User updated.", "success")
    return redirect(url_for("admin_dashboard"))
@app.route(f"/{ADMIN_ROUTE}/message/<public_key>", methods=["POST"])
@require_admin
def add_message(public_key):
    sender_name = (request.form.get("sender_name") or "System").strip()
    body = (request.form.get("body") or "").strip()
    pinned = 1 if request.form.get("pinned") == "1" else 0
    if not body:
        flash("Message cannot be empty.", "error")
        return redirect(url_for("admin_dashboard"))
    db().execute(
        "INSERT INTO messages (user_public_key, sender_name, body, created_at, pinned) VALUES (?, ?, ?, ?, ?)",
        (public_key, sender_name, body, now_iso(), pinned),
    )
    db().commit()
    flash("Message added.", "success")
    return redirect(url_for("admin_dashboard"))
@app.route(f"/{ADMIN_ROUTE}/message/edit/<int:message_id>", methods=["POST"])
@require_admin
def edit_message(message_id):
    sender_name = (request.form.get("sender_name") or "System").strip()
    body = (request.form.get("body") or "").strip()
    pinned = 1 if request.form.get("pinned") == "1" else 0
    if not body:
        flash("Message cannot be empty.", "error")
        return redirect(url_for("admin_dashboard"))
    db().execute(
        "UPDATE messages SET sender_name = ?, body = ?, pinned = ? WHERE id = ?",
        (sender_name, body, pinned, message_id),
    )
    db().commit()
    flash("Message updated.", "success")
    return redirect(url_for("admin_dashboard"))
@app.route(f"/{ADMIN_ROUTE}/message/delete/<int:message_id>", methods=["POST"])
@require_admin
def delete_message(message_id):
    db().execute("DELETE FROM messages WHERE id = ?", (message_id,))
    db().commit()
    flash("Message deleted.", "success")
    return redirect(url_for("admin_dashboard"))
@app.route(f"/{ADMIN_ROUTE}/settings", methods=["POST"])
@require_admin
def update_settings():
    settings = {
        "site_name": request.form.get("site_name", APP_NAME).strip() or APP_NAME,
        "brand_subtitle": request.form.get("brand_subtitle", "").strip(),
        "receipt_heading": request.form.get("receipt_heading", "").strip(),
        "receipt_subheading": request.form.get("receipt_subheading", "").strip(),
        "message_heading": request.form.get("message_heading", "").strip(),
        "footer_note": request.form.get("footer_note", "").strip(),
        "download_link": request.form.get("download_link", "").strip(),
    }
    db().execute(
        """
        UPDATE admin_settings
        SET site_name = ?, brand_subtitle = ?, receipt_heading = ?, receipt_subheading = ?, message_heading = ?, footer_note = ?, download_link = ?
        WHERE id = 1
        """,
        tuple(settings.values()),
    )
    db().commit()
    flash("Settings updated.", "success")
    return redirect(url_for("admin_dashboard"))
@app.route("/api/lookup/<public_key>")
def api_lookup(public_key):
    user = fetch_user(public_key)
    if not user:
        return jsonify({"ok": False, "error": "not_found"}), 404
    messages = db().execute(
        "SELECT id, sender_name, body, created_at, pinned FROM messages WHERE user_public_key = ? ORDER BY pinned DESC, id DESC",
        (public_key,),
    ).fetchall()
    return jsonify(
        {
            "ok": True,
            "user": {
                "public_key": user["public_key"],
                "display_name": user["display_name"],
                "contact_masked": user["contact_masked"],
                "approved": bool(user["approved"]),
                "amount": user["amount"],
                "transaction_cost": user["transaction_cost"],
                "receipt_time": user["receipt_time"],
                "balance": user["balance"],
                "code": user["code"],
                "receipt_note": user["receipt_note"],
                "referrer_public_key": user["referrer_public_key"],
            },
            "messages": [dict(m) for m in messages],
        }
    )
@app.route("/offline")
def offline_page():
    return render_template("offline.html", settings=get_settings())
@app.errorhandler(404)
def not_found(_):
    return render_template("offline.html", settings=get_settings(), message="Page not found"), 404
with app.app_context():
    init_db()
    init_admin_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
