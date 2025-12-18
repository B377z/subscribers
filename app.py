"""
A minimal flask app with:
- An HTML form to collect an email
- Server-side validation
- SQLAlchemy model mapped to a MySQL table
- Comments explaining Python/Flask/SQLAlchemy code
"""

from __future__ import annotations  # allows annotations to be treated as strings
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

# --- Database setup
DB_USER = os.getenv("DB_USER", "dbadmin")
DB_PASS = os.getenv("DB_PASS", "AdminP@ssw0rd!")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_NAME = os.getenv("DB_NAME", "subscribers_db")

# SQLAAlchemy URL format:
db_url = URL.create(
    "mysql+pymysql",  # or 'mysql+mysqldb' if using mysqlclient
    username=DB_USER,
    password=DB_PASS,
    host=DB_HOST,
    database=DB_NAME,
)

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
    if not form.validate_on_submit():
        # flash() stores a message for the next request; requires secret key
        flash("Invalid email address. Please try again.", "error")
        return render_template("index.html", form=form), 400  # Bad Request
    
    email = form.email.data.strip().lower()  # Normalize email
    
    # Use a Session form ORM work; it's a unit of work pattern
    with Session(engine) as session:
        # Check if email already exists
        exists = session.query(Subscriber).filter(Subscriber.email == email).first()
        if exists:
            flash("This email already subscribed.", "info")
        else:
            # Create new Subscriber instance
            sub = Subscriber(email=email)
            session.add(sub)  # Stage for insert
            session.commit()  # Commit transaction
            flash("Subscription successful! Thank you.", "success")
    
    # PRG pattern: Post/Redirect/Get avoids form resubmission prompts       
    return redirect(url_for("index"))

@app.get("/subscribers")
def list_subscribers():
    with Session(engine) as session:
        rows = session.execute(
            select(Subscriber).order_by(Subscriber.created_at.desc())
        ).scalars().all()
    return render_template("subscribers.html", rows=rows)

# --- Entrypoint
if __name__ == "__main__":
    # Flask's dev server; in production use gunicorn/uwsgi
    app.run(host="0.0.0.0", port=5000, debug=True)