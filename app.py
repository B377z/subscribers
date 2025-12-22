"""
A minimal flask app with:
- An HTML form to collect an email
- Server-side validation
- SQLAlchemy model mapped to a DB table (SQLite by default, MySQL optional)
"""

from __future__ import annotations

import os
import logging
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash
from flask_wtf import FlaskForm
from sqlalchemy import String, DateTime, create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email

from azure.monitor.opentelemetry import configure_azure_monitor

# --- Load environment variables from .env (dev convenience)
load_dotenv()

# --- Logging: make sure logs go to stdout (Docker/VM-friendly)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("subscriber-app")

# --- Optional: Azure Monitor / App Insights telemetry
# Requires APPLICATIONINSIGHTS_CONNECTION_STRING
if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    try:
      configure_azure_monitor()
      logger.info("Azure Monitor telemetry enabled")
    except Exception as e:
      logger.error("Failed to enable Azure Monitor telemetry: %s", e)
else:
    logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set; telemetry disabled")

# --- Flask app setup
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-insecure-secret-key")

# --- Database setup
DB_DIALECT = os.getenv("DB_DIALECT", "sqlite").lower()

DB_USER = os.getenv("DB_USER", "dbadmin")
DB_PASS = os.getenv("DB_PASS", "AdminP@ssw0rd!")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_NAME = os.getenv("DB_NAME", "subscribers_db")

if DB_DIALECT == "mysql":
    db_url = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        database=DB_NAME,
    )
elif DB_DIALECT == "sqlite":
    db_url = "sqlite:///subscribers.db"
else:
    raise ValueError(f"Unsupported DB_DIALECT: {DB_DIALECT}")

engine = create_engine(db_url, echo=False, pool_pre_ping=True)

class Base(DeclarativeBase):
    pass

class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

class SubscriberForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Subscribe")

@app.get("/")
def index():
    form = SubscriberForm()
    return render_template("index.html", form=form)

@app.post("/subscribe")
def subscribe():
    form = SubscriberForm()

    if not form.validate_on_submit():
        logger.info("subscribe_invalid")
        flash("Invalid email address. Please try again.", "error")
        return render_template("index.html", form=form), 400

    email = form.email.data.strip().lower()
    logger.info("subscribe_valid email=%s", email)

    with Session(engine) as session:
        existing = session.execute(
            select(Subscriber).where(Subscriber.email == email)
        ).scalar_one_or_none()

        if existing:
            flash("This email is already subscribed.", "info")
        else:
            session.add(Subscriber(email=email))
            session.commit()
            flash("Subscription successful! Thank you.", "success")

    return redirect(url_for("index"))

@app.get("/subscribers")
def list_subscribers():
    with Session(engine) as session:
        rows = session.execute(
            select(Subscriber).order_by(Subscriber.created_at.desc())
        ).scalars().all()

    return render_template("subscribers.html", rows=rows)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
