"""
A minimal flask app with:
- An HTML form to collect an email
- Server-side validation
- SQLAlchemy model mapped to a MySQL table
- Comments explaining Python/Flask/SQLAlchemy code
"""

from __future__ import annotations  # allows annotations to be treated as strings
from logging_config import setup_json_file_logger, new_request_id
import os
from datetime import datetime

from sqlalchemy import select
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from sqlalchemy.engine import URL
from dotenv import load_dotenv

# --- Load Environment variables from .env in dev
load_dotenv()

# --- Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")  # Replace with a secure key in production
log = setup_json_file_logger("subscriber_app")

# --- Database setup
DB_DIALECT = os.getenv("DB_DIALECT", "sqlite")

DB_USER = os.getenv("DB_USER", "dbadmin")
DB_PASS = os.getenv("DB_PASS", "AdminP@ssw0rd!")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_NAME = os.getenv("DB_NAME", "subscribers_db")

# SQLAAlchemy URL format:
if DB_DIALECT == "mysql":
    db_url = URL.create(
        "mysql+pymysql",  # or 'mysql+mysqldb' if using mysqlclient
        username=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        database=DB_NAME,
    )
else:
    # Default to SQLite for simplicity
    db_url = "sqlite:///subscribers.db"

engine = create_engine(db_url, echo=False, pool_pre_ping=True)

# --- SQLAlchemy ORM base class
class Base(DeclarativeBase):
    pass

# --- SQLAlchemy ORM model for the subscribers table
class Subscriber(Base):
    """
    A simple table:
      id          INT primary key (auto)
      email       VARCHAR(320) unique
      created_at  DATETIME
    """
    __tablename__ = "subscribers"
    
    # Mapped[int] tells SQLAlchemy + type checkers the attribute is mapped to a column of int
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # String(320) because RFC suggests emails max ~320 chars (local+domain)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    
# --- Create tables if they don't exist
def init_db():
    Base.metadata.create_all(bind=engine)

# --- Flask-WTF form class for email submission
class SubscriberForm(FlaskForm):
    """
    WTForms defines fields & validators declaratively:
    - DataRequired() ensures field is not empty
    - Email() checks for valid email format
    """
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Subscribe")
    
# --- Routes
@app.before_request
def attach_request_id():
    request.request_id = new_request_id()

@app.after_request
def log_request(response):
    # Build a structured request log event
    log.info(
        "http_request",
        extra={
            "extra": {
                "event": "http_request",
                "request_id": getattr(request, "request_id", None),
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
                "user_agent": request.headers.get("User-Agent"),
            }
        },
    )
    return response

@app.get("/")
def index():
    """
    Render the subscription form on GET /
    """
    form = SubscriberForm()
    return render_template("index.html", form=form)

@app.post("/subscribe")
def subscribe():
    """
    Handle form submission on POST /subscribe
    """
    form = SubscriberForm()

    # 1) Validate input
    if not form.validate_on_submit():
        log.info(
            "subscribe_rejected",
            extra={
                "extra": {
                    "event": "subscribe_rejected",
                    "request_id": getattr(request, "request_id", None),
                    "reason": "validation_failed",
                    "errors": form.errors,  # shows which field failed
                }
            },
        )
        flash("Invalid email address. Please try again.", "error")
        return render_template("index.html", form=form), 400

    email = form.email.data.strip().lower()

    log.info(
        "subscribe_attempt",
        extra={
            "extra": {
                "event": "subscribe_attempt",
                "request_id": request.request_id,
                "email": email,
            }
        },
    )

    # 2) DB work
    with Session(engine) as session:
        exists = session.query(Subscriber).filter(Subscriber.email == email).first()

        if exists:
            log.info(
                "subscribe_duplicate",
                extra={
                    "extra": {
                        "event": "subscribe_duplicate",
                        "request_id": request.request_id,
                        "email": email,
                    }
                },
            )
            flash("This email is already subscribed.", "info")
            return redirect(url_for("index"))

        try:
            sub = Subscriber(email=email)
            session.add(sub)
            session.commit()

            log.info(
                "subscribe_success",
                extra={
                    "extra": {
                        "event": "subscribe_success",
                        "request_id": request.request_id,
                        "email": email,
                    }
                },
            )
            flash("Subscription successful! Thank you.", "success")

        except Exception as e:
            session.rollback()
            log.info(
                "subscribe_db_error",
                extra={
                    "extra": {
                        "event": "subscribe_db_error",
                        "request_id": request.request_id,
                        "email": email,
                        "error": str(e),
                    }
                },
            )
            flash("Something went wrong saving your subscription.", "error")
            return render_template("index.html", form=form), 500

    return redirect(url_for("index"))


@app.get("/subscribers")
def list_subscribers():
    with Session(engine) as session:
        rows = session.execute(
            select(Subscriber).order_by(Subscriber.created_at.desc())
        ).scalars().all()
    return render_template("subscribers.html", rows=rows)

@app.get("/health")
def health():
    # You can later add DB check if you want (optional)
    log.info(
        "health_check",
        extra={"extra": {"event": "health_check", "request_id": getattr(request, "request_id", None), "status": "ok"}},
    )
    return {"status": "ok"}, 200


# --- Entrypoint
if __name__ == "__main__":
    init_db()  # Ensure DB tables exist
    # Note: Do not use app.run() in production; this is only for
    # Flask's dev server; in production use gunicorn/uwsgi
    app.run(host="0.0.0.0", port=5000, debug=True)