
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO

import qrcode
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import asc, desc, func, inspect, or_, text
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "keboma-connect-dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///keboma_connect.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

SITE_TITLE = "KEBoma Connect"
SITE_TAGLINE = "Vacant houses, shops, apartments, AirBnBs, real estate, car hire and online selling."
ROLE_CHOICES = {"tenant": "Tenant", "landlord": "Landlord"}
PUBLIC_ENDPOINTS = {
    "index",
    "hub",
    "explore",
    "listing_detail",
    "chat",
    "support",
    "qr_png",
    "qr_page",
    "manifest",
    "service_worker",
    "icon_svg",
    "robots_txt",
    "sitemap_xml",
    "account",
    "static",
    "api_stats",
    "healthcheck",
    "logout",
}

CATEGORY_LABELS = {
    "vacant_spaces": "Vacant houses and spaces",
    "shops": "Shops",
    "apartments_airbnbs": "Apartments & AirBnBs",
    "real_estate": "Real estate",
    "car_hire": "Cars for hire",
    "online": "Online selling",
}
LANDLORD_LABELS = {
    "vacant_spaces": "Post vacant houses or spaces",
    "shops": "Post a shop or business space",
    "apartments_airbnbs": "Post an apartment or Airbnb",
    "real_estate": "Post real estate",
    "car_hire": "Post a car for hire",
    "online": "Post something online",
}
CATEGORY_TITLES = {
    "vacant_spaces": "Homes, vacant spaces and rentals",
    "shops": "Shops and business spaces",
    "apartments_airbnbs": "Apartments and AirBnBs",
    "real_estate": "Property and land",
    "car_hire": "Cars and vehicle hire",
    "online": "Online products and services",
}
COUNTIES = [
    "Nairobi", "Kiambu", "Kajiado", "Machakos", "Mombasa", "Nakuru", "Kisumu",
    "Uasin Gishu", "Meru", "Nyeri", "Kisii", "Embu", "Kirinyaga", "Murang'a",
    "Busia", "Bungoma", "Vihiga", "Siaya", "Kericho", "Bomet", "Laikipia",
    "Kilifi", "Kwale", "Taita Taveta", "Isiolo", "Narok"
]


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    role = db.Column(db.String(40), nullable=False, default="tenant")
    password_hash = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Listing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(40), nullable=False)
    county = db.Column(db.String(80), nullable=False)
    place = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(220), nullable=True)
    price = db.Column(db.Integer, nullable=False, default=0)
    size_note = db.Column(db.String(80), nullable=True)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    contact_name = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(40), nullable=False)
    whatsapp = db.Column(db.String(120), nullable=True)
    seller_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    seller = db.relationship("User", backref="listings")
    status = db.Column(db.String(30), nullable=False, default="pending")
    interest_count = db.Column(db.Integer, nullable=False, default=0)
    views = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    boosted = db.Column(db.Boolean, default=False)
    featured = db.Column(db.Boolean, default=False)
    is_example = db.Column(db.Boolean, default=False)


class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing.id"), nullable=False)
    listing = db.relationship("Listing", backref="leads")
    visitor_name = db.Column(db.String(120), nullable=False)
    visitor_phone = db.Column(db.String(40), nullable=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="interested")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing.id"), nullable=False)
    listing = db.relationship("Listing", backref="chat_messages")
    sender_name = db.Column(db.String(120), nullable=False)
    sender_role = db.Column(db.String(40), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listing.id"), nullable=True)
    listing = db.relationship("Listing", backref="complaints")
    sender_name = db.Column(db.String(120), nullable=False)
    sender_phone = db.Column(db.String(40), nullable=True)
    subject = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="open")
    reply = db.Column(db.Text, nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def site_url() -> str:
    return os.getenv("SITE_URL") or os.getenv("RENDER_EXTERNAL_URL") or request.url_root.rstrip("/")


def allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg", "webp", "gif"}


def posting_fee(category: str | None, size_note: str | None) -> int:
    category = category or "vacant_spaces"
    note = (size_note or "").lower()
    if category == "vacant_spaces":
        if any(x in note for x in ["bedsitter", "studio"]):
            return 300
        if "1" in note or "one" in note:
            return 400
        if "2" in note or "two" in note:
            return 500
        if "3" in note or "three" in note:
            return 700
        return 500
    if category == "shops":
        return 500
    if category == "apartments_airbnbs":
        return 650
    if category == "real_estate":
        return 1000
    if category == "car_hire":
        return 450
    if category == "online":
        return 350
    return 500


def parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def serialize_datetime(value):
    return value.isoformat() if isinstance(value, datetime) else None


def get_current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def current_admin():
    aid = session.get("admin_id")
    return db.session.get(User, aid) if aid else None


def has_admin() -> bool:
    return db.session.query(User.id).filter(User.role == "admin").first() is not None


def real_listings_exist() -> bool:
    return db.session.query(Listing.id).filter(
        Listing.is_example.is_(False),
        Listing.status == "available",
    ).first() is not None


def visible_listing_query():
    q = Listing.query.filter(Listing.status == "available")
    if real_listings_exist():
        q = q.filter(Listing.is_example.is_(False))
    return q


def visible_single_listing(listing_id: int):
    listing = db.session.get(Listing, listing_id)
    if not listing:
        return None
    if listing.status == "pending" and not can_manage_listing(listing):
        return None
    if listing.is_example and real_listings_exist() and not can_manage_listing(listing):
        return None
    return listing


def can_manage_listing(listing: Listing) -> bool:
    admin = current_admin()
    if admin:
        return True
    user = get_current_user()
    return bool(user and user.id == listing.seller_user_id)


def is_authenticated_landlord() -> bool:
    user = get_current_user()
    return bool(user and user.role == "landlord" and user.password_hash)


def ensure_tenant_user():
    user = get_current_user()
    if user:
        return user
    display_name = (session.get("guest_name") or "Guest").strip() or "Guest"
    role = session.get("role") or "tenant"
    user = User(display_name=display_name, role=role)
    db.session.add(user)
    db.session.commit()
    session["user_id"] = user.id
    return user


def seed_data():
    if Listing.query.count():
        return
    owner = User(display_name="KEBoma Desk", phone="07xx xxx xxx", role="landlord")
    db.session.add(owner)
    db.session.flush()
    samples = [
        dict(title="2 Bedroom Apartment in Ruaka", category="apartments_airbnbs", county="Kiambu", place="Ruaka", address="Near the bypass", price=28000, size_note="2 Bedroom", description="Bright rooms, secure compound, water available, and close to transport.", contact_name="Mercy", contact_phone="07xx xxx xxx", whatsapp="https://wa.me/254700000000", image_url="https://images.unsplash.com/photo-1560185007-5f0bb1866cab?auto=format&fit=crop&w=1200&q=80", is_example=True),
        dict(title="Clean Barber Space in South B", category="shops", county="Nairobi", place="South B", address="Main road corner", price=15000, size_note="Business space", description="Ideal for barber shop, salon, nail studio, or beauty services.", contact_name="John", contact_phone="07xx xxx xxx", whatsapp="https://wa.me/254711111111", image_url="https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?auto=format&fit=crop&w=1200&q=80", is_example=True),
        dict(title="Prime Plot in Kitengela", category="real_estate", county="Kajiado", place="Kitengela", address="1.2 km from tarmac", price=2500000, size_note="Plot", description="Flat land, ready documents, and good access road.", contact_name="Brian", contact_phone="07xx xxx xxx", whatsapp="https://wa.me/254733333333", image_url="https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1200&q=80", is_example=True),
        dict(title="Toyota Fielder 2016 Clean - For Hire", category="car_hire", county="Nairobi", place="CBD", address="Inspection by appointment", price=4500, size_note="Car hire", description="Very clean, fuel efficient, and well maintained for daily hire.", contact_name="Zoe", contact_phone="07xx xxx xxx", whatsapp="https://wa.me/254744444444", image_url="https://images.unsplash.com/photo-1494976388531-d1058494cdd8?auto=format&fit=crop&w=1200&q=80", is_example=True),
        dict(title="Online Mini-Mart Delivery Offer", category="online", county="Mombasa", place="Nyali", address="Delivery region included", price=3500, size_note="Online", description="For deliveries, products, and social media selling.", contact_name="Asha", contact_phone="07xx xxx xxx", whatsapp="https://wa.me/254755555555", image_url="https://images.unsplash.com/photo-1556742400-b5d3b4b7f4c8?auto=format&fit=crop&w=1200&q=80", is_example=True),
    ]
    for idx, data in enumerate(samples):
        db.session.add(
            Listing(
                seller_user_id=owner.id,
                expires_at=datetime.utcnow() + timedelta(days=14),
                boosted=idx < 2,
                featured=idx == 0,
                status="available",
                **data,
            )
        )
    db.session.commit()


def expire_due_listings():
    now = datetime.utcnow()
    changed = False
    for listing in Listing.query.filter(Listing.status == "available").all():
        if listing.expires_at and now > listing.expires_at:
            listing.status = "paused"
            changed = True
    if changed:
        db.session.commit()


def migrate_schema():
    insp = inspect(db.engine)
    if not insp.has_table("listing"):
        return
    cols = {c["name"] for c in insp.get_columns("listing")}
    with db.engine.begin() as conn:
        if "size_note" not in cols:
            conn.execute(text("ALTER TABLE listing ADD COLUMN size_note VARCHAR(80)"))
        if "is_example" not in cols:
            conn.execute(text("ALTER TABLE listing ADD COLUMN is_example BOOLEAN DEFAULT 0"))


def listing_payload(listing: Listing) -> dict:
    return {
        "id": listing.id,
        "title": listing.title,
        "category": listing.category,
        "county": listing.county,
        "place": listing.place,
        "address": listing.address,
        "price": listing.price,
        "size_note": listing.size_note,
        "description": listing.description,
        "image_url": listing.image_url,
        "contact_name": listing.contact_name,
        "contact_phone": listing.contact_phone,
        "whatsapp": listing.whatsapp,
        "seller_user_id": listing.seller_user_id,
        "status": listing.status,
        "interest_count": listing.interest_count,
        "views": listing.views,
        "created_at": serialize_datetime(listing.created_at),
        "expires_at": serialize_datetime(listing.expires_at),
        "boosted": listing.boosted,
        "featured": listing.featured,
        "is_example": listing.is_example,
    }


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "phone": user.phone,
        "role": user.role,
        "password_hash": user.password_hash,
        "created_at": serialize_datetime(user.created_at),
    }


def lead_payload(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "listing_id": lead.listing_id,
        "visitor_name": lead.visitor_name,
        "visitor_phone": lead.visitor_phone,
        "message": lead.message,
        "status": lead.status,
        "created_at": serialize_datetime(lead.created_at),
    }


def chat_payload(msg: ChatMessage) -> dict:
    return {
        "id": msg.id,
        "listing_id": msg.listing_id,
        "sender_name": msg.sender_name,
        "sender_role": msg.sender_role,
        "message": msg.message,
        "created_at": serialize_datetime(msg.created_at),
    }


def complaint_payload(item: Complaint) -> dict:
    return {
        "id": item.id,
        "listing_id": item.listing_id,
        "sender_name": item.sender_name,
        "sender_phone": item.sender_phone,
        "subject": item.subject,
        "message": item.message,
        "status": item.status,
        "reply": item.reply,
        "replied_at": serialize_datetime(item.replied_at),
        "created_at": serialize_datetime(item.created_at),
    }


def export_backup() -> dict:
    return {
        "site_title": SITE_TITLE,
        "exported_at": datetime.utcnow().isoformat(),
        "users": [user_payload(u) for u in User.query.order_by(User.id.asc()).all()],
        "listings": [listing_payload(l) for l in Listing.query.order_by(Listing.id.asc()).all()],
        "leads": [lead_payload(l) for l in Lead.query.order_by(Lead.id.asc()).all()],
        "chat_messages": [chat_payload(m) for m in ChatMessage.query.order_by(ChatMessage.id.asc()).all()],
        "complaints": [complaint_payload(c) for c in Complaint.query.order_by(Complaint.id.asc()).all()],
    }


def restore_backup(payload: dict) -> dict:
    users = payload.get("users", [])
    listings = payload.get("listings", [])
    leads = payload.get("leads", [])
    chat_messages = payload.get("chat_messages", [])
    complaints = payload.get("complaints", [])

    db.session.query(ChatMessage).delete()
    db.session.query(Lead).delete()
    db.session.query(Complaint).delete()
    db.session.query(Listing).delete()
    db.session.query(User).delete()
    db.session.commit()

    user_map = {}
    for row in users:
        user = User(
            id=row.get("id"),
            display_name=row.get("display_name") or "User",
            phone=row.get("phone"),
            role=row.get("role") or "tenant",
            password_hash=row.get("password_hash"),
            created_at=parse_datetime(row.get("created_at")) or datetime.utcnow(),
        )
        db.session.add(user)
        user_map[user.id] = user

    db.session.flush()

    listing_map = {}
    for row in listings:
        listing = Listing(
            id=row.get("id"),
            title=row.get("title") or "Untitled",
            category=row.get("category") or "vacant_spaces",
            county=row.get("county") or "Nairobi",
            place=row.get("place") or "Town",
            address=row.get("address"),
            price=int(row.get("price") or 0),
            size_note=row.get("size_note"),
            description=row.get("description"),
            image_url=row.get("image_url"),
            contact_name=row.get("contact_name") or "Owner",
            contact_phone=row.get("contact_phone") or "N/A",
            whatsapp=row.get("whatsapp"),
            seller_user_id=row.get("seller_user_id"),
            status=row.get("status") or "pending",
            interest_count=int(row.get("interest_count") or 0),
            views=int(row.get("views") or 0),
            created_at=parse_datetime(row.get("created_at")) or datetime.utcnow(),
            expires_at=parse_datetime(row.get("expires_at")) or (datetime.utcnow() + timedelta(days=14)),
            boosted=bool(row.get("boosted")),
            featured=bool(row.get("featured")),
            is_example=bool(row.get("is_example")),
        )
        db.session.add(listing)
        listing_map[listing.id] = listing

    db.session.flush()

    for row in leads:
        db.session.add(
            Lead(
                id=row.get("id"),
                listing_id=row.get("listing_id"),
                visitor_name=row.get("visitor_name") or "Visitor",
                visitor_phone=row.get("visitor_phone"),
                message=row.get("message"),
                status=row.get("status") or "interested",
                created_at=parse_datetime(row.get("created_at")) or datetime.utcnow(),
            )
        )

    for row in chat_messages:
        db.session.add(
            ChatMessage(
                id=row.get("id"),
                listing_id=row.get("listing_id"),
                sender_name=row.get("sender_name") or "Admin",
                sender_role=row.get("sender_role") or "visitor",
                message=row.get("message") or "",
                created_at=parse_datetime(row.get("created_at")) or datetime.utcnow(),
            )
        )

    for row in complaints:
        db.session.add(
            Complaint(
                id=row.get("id"),
                listing_id=row.get("listing_id"),
                sender_name=row.get("sender_name") or "User",
                sender_phone=row.get("sender_phone"),
                subject=row.get("subject") or "Complaint",
                message=row.get("message") or "",
                status=row.get("status") or "open",
                reply=row.get("reply"),
                replied_at=parse_datetime(row.get("replied_at")),
                created_at=parse_datetime(row.get("created_at")) or datetime.utcnow(),
            )
        )

    db.session.commit()
    return {"users": len(users), "listings": len(listings), "leads": len(leads), "chat_messages": len(chat_messages), "complaints": len(complaints)}


@app.context_processor
def inject_globals():
    page_title = SITE_TITLE
    page_description = SITE_TAGLINE
    return dict(
        site_title=SITE_TITLE,
        site_tagline=SITE_TAGLINE,
        counties=COUNTIES,
        categories=CATEGORY_LABELS,
        role=session.get("role", ""),
        nav_user=get_current_user(),
        nav_admin=current_admin(),
        site_url=site_url() if request else "",
        fee_lookup=posting_fee,
        page_title=page_title,
        page_description=page_description,
    )


@app.before_request
def boot_and_gate():
    db.create_all()
    migrate_schema()
    seed_data()
    expire_due_listings()
    endpoint = request.endpoint or ""
    if endpoint in PUBLIC_ENDPOINTS or endpoint.startswith("static") or endpoint.startswith("admin_"):
        return
    if not session.get("role"):
        return redirect(url_for("index"))


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        role = request.form.get("role", "tenant")
        if role not in ROLE_CHOICES:
            role = "tenant"
        session["role"] = role
        session["guest_name"] = request.form.get("name", "").strip()[:120] or session.get("guest_name", "Guest")
        return redirect(url_for("hub"))
    return render_template(
        "index.html",
        page_title=f"{SITE_TITLE} | Welcome",
        page_description=SITE_TAGLINE,
    )


@app.route("/hub")
def hub():
    role = session.get("role")
    if role not in ROLE_CHOICES:
        return redirect(url_for("index"))
    cards = []
    for key, label in CATEGORY_LABELS.items():
        href = url_for("post_listing", category=key) if role == "landlord" else url_for("explore", category=key)
        title = LANDLORD_LABELS[key] if role == "landlord" else label
        cards.append({"key": key, "title": title, "subtitle": CATEGORY_TITLES[key], "href": href})
    return render_template(
        "hub.html",
        cards=cards,
        role=role,
        page_title=f"{SITE_TITLE} | Hub",
        page_description="Choose a marketplace path for homes, shops, apartments, AirBnBs, real estate, car hire and online selling.",
    )


@app.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":
        action = request.form.get("action", "register")
        phone = request.form.get("phone", "").strip()[:40]
        password = request.form.get("password", "")
        display_name = request.form.get("display_name", "").strip()[:120] or "Landlord"
        if action == "register":
            if not phone or not password:
                flash("Phone and password are required.", "danger")
                return redirect(url_for("account"))
            existing = User.query.filter(User.phone == phone, User.role == "landlord").first()
            if existing:
                flash("That account already exists. Please log in.", "warning")
                return redirect(url_for("account"))
            user = User(display_name=display_name, phone=phone, role="landlord", password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            session["role"] = "landlord"
            session["guest_name"] = user.display_name
            flash("Account created. You can post now.", "success")
            return redirect(url_for("dashboard"))
        if action == "login":
            user = User.query.filter(User.phone == phone, User.role == "landlord").first()
            if user and user.password_hash and check_password_hash(user.password_hash, password):
                session["user_id"] = user.id
                session["role"] = "landlord"
                session["guest_name"] = user.display_name
                flash("Welcome back.", "success")
                return redirect(url_for("dashboard"))
            flash("Wrong phone or password.", "danger")
            return redirect(url_for("account"))
    return render_template(
        "account.html",
        page_title=f"{SITE_TITLE} | Account",
        page_description="Create or open a landlord account to post listings and manage inbox messages.",
    )


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("admin_id", None)
    session.pop("guest_name", None)
    session.pop("role", None)
    flash("Signed out.", "info")
    return redirect(url_for("index"))


@app.route("/explore")
def explore():
    category = request.args.get("category", "vacant_spaces")
    if category not in CATEGORY_LABELS and category != "all":
        category = "vacant_spaces"
    county = request.args.get("county", "").strip()
    place = request.args.get("place", "").strip()
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "featured")
    query = visible_listing_query()
    if category and category != "all":
        query = query.filter_by(category=category)
    if county:
        query = query.filter(Listing.county.ilike(f"%{county}%"))
    if place:
        query = query.filter(or_(Listing.place.ilike(f"%{place}%"), Listing.address.ilike(f"%{place}%")))
    if q:
        query = query.filter(or_(
            Listing.title.ilike(f"%{q}%"),
            Listing.description.ilike(f"%{q}%"),
            Listing.place.ilike(f"%{q}%"),
            Listing.county.ilike(f"%{q}%"),
            Listing.address.ilike(f"%{q}%"),
            Listing.size_note.ilike(f"%{q}%"),
        ))
    if sort == "latest":
        query = query.order_by(desc(Listing.created_at))
    elif sort == "price_low":
        query = query.order_by(asc(Listing.price))
    elif sort == "price_high":
        query = query.order_by(desc(Listing.price))
    elif sort == "random":
        query = query.order_by(func.random())
    else:
        query = query.order_by(desc(Listing.boosted), desc(Listing.featured), desc(Listing.interest_count), desc(Listing.created_at))
    listings = query.all()
    featured = visible_listing_query().filter(Listing.featured.is_(True)).order_by(desc(Listing.created_at)).limit(3).all()
    return render_template(
        "explore.html",
        listings=listings,
        featured=featured,
        category=category,
        county=county,
        place=place,
        q=q,
        sort=sort,
        page_title=f"{SITE_TITLE} | Explore",
        page_description="Browse available vacant houses, shops, apartments, AirBnBs, real estate, car hire and online listings.",
    )


@app.route("/listing/<int:listing_id>", methods=["GET", "POST"])
def listing_detail(listing_id):
    listing = visible_single_listing(listing_id)
    if not listing:
        abort(404)

    listing.views += 1
    db.session.commit()

    user = get_current_user()
    admin = current_admin()
    can_manage = can_manage_listing(listing)

    if request.method == "POST":
        action = request.form.get("action")
        visitor_name = request.form.get("visitor_name", session.get("guest_name", "Guest")).strip()[:120] or "Guest"
        visitor_phone = request.form.get("visitor_phone", "").strip()[:40]
        message = request.form.get("message", "").strip()

        if action == "interest":
            listing.interest_count += 1
            db.session.add(Lead(listing_id=listing.id, visitor_name=visitor_name, visitor_phone=visitor_phone, message=message or "Interested", status="interested"))
            db.session.commit()
            flash("Interest recorded.", "success")
        elif action == "chat":
            if not message:
                flash("Write a message first.", "warning")
            else:
                db.session.add(ChatMessage(listing_id=listing.id, sender_name=visitor_name, sender_role="visitor", message=message))
                db.session.commit()
                flash("Message sent.", "success")
        elif action == "continue" and can_manage:
            listing.expires_at = datetime.utcnow() + timedelta(days=14)
            if listing.status != "taken":
                listing.status = "available"
            db.session.commit()
            flash("Listing renewed for 14 days.", "success")
        elif action == "pause" and can_manage:
            listing.status = "paused"
            db.session.commit()
            flash("Listing paused.", "info")
        elif action == "mark_taken":
            user = get_current_user()
            if not user or user.role != "landlord" or user.id != listing.seller_user_id:
                flash("Only the landlord can mark this listing as taken.", "warning")
            else:
                listing.status = "taken"
                db.session.commit()
                flash("Listing marked as taken.", "success")
        else:
            flash("You are not allowed to do that.", "warning")
        return redirect(url_for("listing_detail", listing_id=listing.id))

    expiring_soon = listing.expires_at - datetime.utcnow() <= timedelta(days=2)
    return render_template(
        "listing.html",
        listing=listing,
        expiring_soon=expiring_soon,
        can_manage=can_manage,
        owner=user,
        admin=admin,
        page_title=f"{listing.title} | {SITE_TITLE}",
        page_description=(listing.description or SITE_TAGLINE)[:160],
    )


@app.route("/post", methods=["GET", "POST"])
def post_listing():
    role = session.get("role")
    if role != "landlord":
        return redirect(url_for("hub"))
    if not is_authenticated_landlord():
        return redirect(url_for("account"))

    if request.method == "POST":
        user = get_current_user()
        if not user or user.role != "landlord":
            flash("Create a landlord account first.", "warning")
            return redirect(url_for("account"))

        title = request.form.get("title", "").strip()
        category = request.form.get("category", "vacant_spaces")
        if category not in CATEGORY_LABELS:
            category = "vacant_spaces"
        county = request.form.get("county", "").strip()
        place = request.form.get("place", "").strip()
        address = request.form.get("address", "").strip()
        price = int(request.form.get("price") or 0)
        size_note = request.form.get("size_note", "").strip()
        description = request.form.get("description", "").strip()
        contact_name = request.form.get("contact_name", user.display_name).strip() or user.display_name
        contact_phone = request.form.get("contact_phone", user.phone or "").strip()
        whatsapp = request.form.get("whatsapp", "").strip()
        boosted = request.form.get("boosted") == "on"
        featured = request.form.get("featured") == "on"
        image_url = request.form.get("image_url", "").strip() or None
        uploaded = request.files.get("image_file")
        stored_image = image_url

        if uploaded and uploaded.filename:
            if not allowed_image(uploaded.filename):
                flash("Please upload a PNG, JPG, JPEG, WEBP or GIF image.", "danger")
                return redirect(url_for("post_listing", category=category))
            ext = uploaded.filename.rsplit(".", 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            uploaded.save(path)
            stored_image = url_for("static", filename=f"uploads/{filename}")

        if not all([title, county, place, price, contact_name, contact_phone]):
            flash("Please complete the required fields.", "danger")
            return redirect(url_for("post_listing", category=category))

        listing = Listing(
            title=title,
            category=category,
            county=county,
            place=place,
            address=address,
            price=price,
            size_note=size_note,
            description=description,
            image_url=stored_image,
            contact_name=contact_name,
            contact_phone=contact_phone,
            whatsapp=whatsapp or None,
            seller_user_id=user.id,
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=14),
            boosted=boosted,
            featured=featured,
            is_example=False,
        )
        db.session.add(listing)
        db.session.commit()
        session["last_fee"] = posting_fee(category, size_note)
        flash("Listing submitted for admin approval.", "success")
        return redirect(url_for("dashboard"))

    category = request.args.get("category", "vacant_spaces")
    if category not in CATEGORY_LABELS:
        category = "vacant_spaces"
    return render_template(
        "post_listing.html",
        posting_fee=posting_fee,
        category=category,
        page_title=f"{SITE_TITLE} | Post listing",
        page_description="Post a vacant house, shop, apartment, Airbnb, real estate item, car hire listing or online offer.",
    )


@app.route("/dashboard")
def dashboard():
    role = session.get("role")
    if role != "landlord":
        return redirect(url_for("hub"))
    if not is_authenticated_landlord():
        return redirect(url_for("account"))

    user = get_current_user()
    if role == "landlord" and user:
        my_listings = Listing.query.filter_by(seller_user_id=user.id).order_by(desc(Listing.created_at)).all()
        my_leads = Lead.query.join(Listing).filter(Listing.seller_user_id == user.id).order_by(desc(Lead.created_at)).all()
        my_messages = ChatMessage.query.join(Listing).filter(Listing.seller_user_id == user.id).order_by(desc(ChatMessage.created_at)).limit(30).all()
    else:
        my_listings = []
        my_leads = []
        my_messages = []
    return render_template(
        "dashboard.html",
        my_listings=my_listings,
        my_leads=my_leads,
        my_messages=my_messages,
        page_title=f"{SITE_TITLE} | Dashboard",
        page_description="See your listings, leads, approvals and messages in one place.",
    )


@app.route("/chat/<int:listing_id>", methods=["GET", "POST"])
def chat(listing_id):
    listing = visible_single_listing(listing_id)
    if not listing:
        abort(404)

    if request.method == "POST":
        sender_name = request.form.get("sender_name", session.get("guest_name", "Guest")).strip()[:120] or "Guest"
        message = request.form.get("message", "").strip()
        if message:
            db.session.add(ChatMessage(listing_id=listing.id, sender_name=sender_name, sender_role="visitor", message=message))
            db.session.commit()
            flash("Your private message was sent.", "success")
        return redirect(url_for("chat", listing_id=listing.id))

    messages = ChatMessage.query.filter_by(listing_id=listing.id).order_by(ChatMessage.created_at.asc()).all()
    return render_template(
        "chat.html",
        listing=listing,
        messages=messages,
        page_title=f"Chat | {listing.title}",
        page_description="Private listing conversation.",
    )


@app.route("/api/stats")
def api_stats():
    active = visible_listing_query().count()
    online = 1000 + active * 19 + (datetime.utcnow().minute % 20) * 17
    return jsonify({
        "listings": active,
        "online": online,
        "interested": Lead.query.count(),
        "messages": ChatMessage.query.count(),
    })


@app.route("/support", methods=["GET", "POST"])
def support():
    ticket = request.args.get("ticket", type=int)
    ticket_item = db.session.get(Complaint, ticket) if ticket else None
    if request.method == "POST":
        sender_name = request.form.get("sender_name", session.get("guest_name", "Guest")).strip()[:120] or "Guest"
        sender_phone = request.form.get("sender_phone", "").strip()[:40]
        subject = request.form.get("subject", "General complaint").strip()[:180] or "General complaint"
        message = request.form.get("message", "").strip()
        listing_id = request.form.get("listing_id", type=int)
        if not message:
            flash("Write your complaint or question first.", "warning")
            return redirect(url_for("support"))
        complaint = Complaint(
            listing_id=listing_id,
            sender_name=sender_name,
            sender_phone=sender_phone,
            subject=subject,
            message=message,
        )
        db.session.add(complaint)
        db.session.commit()
        flash(f"Complaint received. Your ticket number is {complaint.id}.", "success")
        return redirect(url_for("support", ticket=complaint.id))
    return render_template(
        "support.html",
        ticket_item=ticket_item,
        page_title=f"{SITE_TITLE} | Support",
        page_description="Send complaints and questions to the admin desk.",
    )


@app.route("/qr.png")
def qr_png():
    target = request.args.get("target") or site_url()
    img = qrcode.make(target)
    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return send_file(bio, mimetype="image/png", as_attachment=False, download_name="keboma-connect-qr.png")


@app.route("/qr")
def qr_page():
    target = request.args.get("target") or site_url()
    return render_template(
        "qr.html",
        qr_target=target,
        page_title=f"{SITE_TITLE} | QR",
        page_description="Download a QR code for posters, stickers and notice boards.",
    )


@app.route("/manifest.webmanifest")
def manifest():
    data = {
        "name": SITE_TITLE,
        "short_name": "KEBoma",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "theme_color": "#5b7cff",
        "background_color": "#f5f7fb",
        "icons": [
            {"src": url_for("icon_svg"), "sizes": "any", "type": "image/svg+xml"},
        ],
    }
    return Response(json.dumps(data), mimetype="application/manifest+json")


@app.route("/sw.js")
def service_worker():
    script = r"""
const CACHE_NAME = 'keboma-connect-v1';
const CORE_ASSETS = [
  '/',
  '/hub',
  '/explore?category=vacant_spaces',
  '/explore?category=shops',
  '/explore?category=apartments_airbnbs',
  '/explore?category=real_estate',
  '/explore?category=car_hire',
  '/explore?category=online',
  '/qr',
  '/support',
  '/manifest.webmanifest',
  '/icon.svg'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(CORE_ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.map(key => key !== CACHE_NAME ? caches.delete(key) : null)))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith((async () => {
    try {
      const networkResponse = await fetch(event.request);
      const cache = await caches.open(CACHE_NAME);
      cache.put(event.request, networkResponse.clone());
      return networkResponse;
    } catch (_) {
      const cached = await caches.match(event.request);
      if (cached) return cached;
      if (event.request.destination === 'document') {
        const fallback = await caches.match('/');
        if (fallback) return fallback;
      }
      return new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
    }
  })());
});
"""
    return Response(script, mimetype="application/javascript")


@app.route("/icon.svg")
def icon_svg():
    svg = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="KEBoma Connect">
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop stop-color="#5b7cff" offset="0%"/>
      <stop stop-color="#7ea1ff" offset="100%"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="url(#g)"/>
  <path d="M118 329V183h44v58l53-58h54l-68 73 76 73h-58l-57-56v56h-44zm224 0-38-58-14 15v43h-40V183h40v70l61-70h52l-70 77 74 69h-56l-9-13z" fill="#fff"/>
</svg>
""".strip()
    return Response(svg, mimetype="image/svg+xml")


@app.route("/robots.txt")
def robots_txt():
    text_body = f"""User-agent: *
Allow: /

Sitemap: {site_url()}/sitemap.xml
"""
    return Response(text_body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    pages = [
        url_for("index", _external=True),
        url_for("hub", _external=True),
        url_for("account", _external=True),
        url_for("support", _external=True),
        url_for("qr_page", _external=True),
        url_for("explore", category="vacant_spaces", _external=True),
        url_for("explore", category="shops", _external=True),
        url_for("explore", category="apartments_airbnbs", _external=True),
        url_for("explore", category="real_estate", _external=True),
        url_for("explore", category="car_hire", _external=True),
        url_for("explore", category="online", _external=True),
    ]
    items = "\n".join(f"<url><loc>{page}</loc></url>" for page in pages)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>
"""
    return Response(xml, mimetype="application/xml")


@app.route("/seed-refresh")
def seed_refresh():
    if request.args.get("token") != os.getenv("ADMIN_TOKEN", "demo"):
        abort(403)
    db.drop_all()
    db.create_all()
    migrate_schema()
    seed_data()
    return "reset complete"


@app.route("/buh", methods=["GET", "POST"])
def buh():
    admin = current_admin()
    if admin:
        stats = {
            "users": User.query.count(),
            "admins": User.query.filter(User.role == "admin").count(),
            "listings": Listing.query.count(),
            "pending": Listing.query.filter(Listing.status == "pending").count(),
            "real_listings": Listing.query.filter(Listing.is_example.is_(False)).count(),
            "leads": Lead.query.count(),
            "messages": ChatMessage.query.count(),
        }
        all_listings = Listing.query.order_by(desc(Listing.created_at)).limit(40).all()
        all_users = User.query.order_by(desc(User.created_at)).limit(20).all()
        pending_listings = Listing.query.filter(Listing.status == "pending").order_by(desc(Listing.created_at)).all()
        recent_messages = ChatMessage.query.order_by(desc(ChatMessage.created_at)).limit(40).all()
        complaints = Complaint.query.order_by(desc(Complaint.created_at)).limit(30).all()
        return render_template(
            "admin.html",
            admin=admin,
            stats=stats,
            all_listings=all_listings,
            all_users=all_users,
            pending_listings=pending_listings,
            recent_messages=recent_messages,
            complaints=complaints,
            admin_mode="dashboard",
            page_title=f"{SITE_TITLE} | Admin",
            page_description="Admin moderation, approvals, messages, backup and restore.",
        )

    has_admin_user = has_admin()
    if request.method == "POST":
        action = request.form.get("action")
        password = request.form.get("password", "")
        display_name = request.form.get("display_name", "Admin").strip() or "Admin"
        phone = request.form.get("phone", "").strip()[:40]
        if action == "register":
            if has_admin_user:
                flash("Admin already exists. Please log in.", "warning")
                return redirect(url_for("buh"))
            username = request.form.get("username", "").strip()
            if not username or not password:
                flash("Enter username and password to register.", "danger")
                return redirect(url_for("buh"))
            admin_user = User(display_name=display_name, phone=phone, role="admin", password_hash=generate_password_hash(password))
            db.session.add(admin_user)
            db.session.commit()
            session["admin_id"] = admin_user.id
            flash("Admin registered successfully.", "success")
            return redirect(url_for("buh"))
        if action == "login":
            admin_user = User.query.filter(User.role == "admin").order_by(User.created_at.asc()).first()
            if admin_user and admin_user.password_hash and check_password_hash(admin_user.password_hash, password):
                session["admin_id"] = admin_user.id
                flash("Welcome, admin.", "success")
                return redirect(url_for("buh"))
            flash("Wrong admin password.", "danger")
            return redirect(url_for("buh"))

    admin_mode = "login" if has_admin_user else "register"
    return render_template(
        "admin.html",
        admin=None,
        admin_mode=admin_mode,
        page_title=f"{SITE_TITLE} | Admin",
        page_description="Admin login and registration.",
    )


@app.route("/buh/approve/<int:listing_id>", methods=["POST"])
def admin_approve_listing(listing_id):
    admin = current_admin()
    if not admin:
        abort(403)
    listing = db.session.get(Listing, listing_id)
    if not listing:
        abort(404)
    listing.status = "available"
    db.session.commit()
    flash(f"Approved listing #{listing.id}.", "success")
    return redirect(url_for("buh"))


@app.route("/buh/reject/<int:listing_id>", methods=["POST"])
def admin_reject_listing(listing_id):
    admin = current_admin()
    if not admin:
        abort(403)
    listing = db.session.get(Listing, listing_id)
    if not listing:
        abort(404)
    listing.status = "paused"
    db.session.commit()
    flash(f"Listing #{listing.id} moved to paused.", "info")
    return redirect(url_for("buh"))


@app.route("/buh/reply/<int:complaint_id>", methods=["POST"])
def admin_reply_complaint(complaint_id):
    admin = current_admin()
    if not admin:
        abort(403)
    complaint = db.session.get(Complaint, complaint_id)
    if not complaint:
        abort(404)
    reply = request.form.get("reply", "").strip()
    if not reply:
        flash("Write a reply first.", "warning")
        return redirect(url_for("buh"))
    complaint.reply = reply
    complaint.status = "replied"
    complaint.replied_at = datetime.utcnow()
    db.session.commit()
    flash(f"Reply saved for ticket #{complaint.id}.", "success")
    return redirect(url_for("buh"))


@app.route("/buh/message/<int:listing_id>", methods=["POST"])
def admin_reply_message(listing_id):
    admin = current_admin()
    if not admin:
        abort(403)
    listing = db.session.get(Listing, listing_id)
    if not listing:
        abort(404)
    message = request.form.get("message", "").strip()
    if not message:
        flash("Write a message first.", "warning")
        return redirect(url_for("buh"))
    db.session.add(ChatMessage(listing_id=listing.id, sender_name=admin.display_name, sender_role="admin", message=message))
    db.session.commit()
    flash(f"Reply sent for listing #{listing.id}.", "success")
    return redirect(url_for("buh"))


@app.route("/buh/export")
def admin_export_backup():
    admin = current_admin()
    if not admin:
        abort(403)
    payload = export_backup()
    data = json.dumps(payload, indent=2).encode("utf-8")
    return send_file(
        BytesIO(data),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"keboma-connect-backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json",
    )


@app.route("/buh/import", methods=["POST"])
def admin_import_backup():
    admin = current_admin()
    if not admin:
        abort(403)
    upload = request.files.get("backup_file")
    if not upload or not upload.filename:
        flash("Choose a backup file first.", "warning")
        return redirect(url_for("buh"))
    try:
        payload = json.load(upload.stream)
        counts = restore_backup(payload)
        flash(
            f"Backup restored: {counts['users']} users, {counts['listings']} listings, {counts['leads']} leads, {counts['chat_messages']} messages, {counts['complaints']} complaints.",
            "success",
        )
    except Exception as exc:
        db.session.rollback()
        flash(f"Restore failed: {exc}", "danger")
    return redirect(url_for("buh"))


@app.route("/buh/logout")
def admin_logout():
    session.pop("admin_id", None)
    flash("Admin logged out.", "info")
    return redirect(url_for("buh"))


@app.route("/health")
def healthcheck():
    return "ok"


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        migrate_schema()
        seed_data()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
