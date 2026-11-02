import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-deploying")
database_url = os.environ.get("DATABASE_URL", "sqlite:///rurallearn.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
CORS(app, resources={r"/api/*": {"origins": "*"}})

serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    subject = db.Column(db.String(120), default="")
    description = db.Column(db.Text, default="")
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    join_code = db.Column(db.String(12), unique=True, nullable=False)

class Membership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending or approved

class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    video_url = db.Column(db.String(500), nullable=False)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def user_data(user):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}

def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header.replace("Bearer ", "", 1) if header.startswith("Bearer ") else ""
        if not token:
            return jsonify(error="Please log in first."), 401
        try:
            payload = serializer.loads(token, max_age=60 * 60 * 24 * 7)
            g.user = db.session.get(User, payload.get("user_id"))
        except (BadSignature, SignatureExpired):
            return jsonify(error="Session expired. Please log in again."), 401
        if not g.user:
            return jsonify(error="Account not found."), 401
        return fn(*args, **kwargs)
    return wrapper

@app.get("/")
def home():
    return jsonify(message="RuralLearn backend is running.", status="ok")

@app.get("/api/health")
def health():
    return jsonify(status="ok", service="RuralLearn API")

@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "student").lower()
    if not name or not email or len(password) < 6:
        return jsonify(error="Name, email, and a password of at least 6 characters are required."), 400
    if role not in ("student", "teacher"):
        return jsonify(error="Role must be student or teacher."), 400
    if User.query.filter_by(email=email).first():
        return jsonify(error="An account with this email already exists."), 409
    user = User(name=name, email=email, password_hash=generate_password_hash(password), role=role)
    db.session.add(user)
    db.session.commit()
    token = serializer.dumps({"user_id": user.id})
    return jsonify(message="Account created.", token=token, user=user_data(user)), 201

@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify(error="Incorrect email or password."), 401
    token = serializer.dumps({"user_id": user.id})
    return jsonify(message="Login successful.", token=token, user=user_data(user))

@app.get("/api/me")
@auth_required
def me():
    return jsonify(user=user_data(g.user))

@app.post("/api/classrooms")
@auth_required
def create_classroom():
    if g.user.role != "teacher":
        return jsonify(error="Only teachers can create classrooms."), 403
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="Classroom title is required."), 400
    import secrets
    classroom = Classroom(
        title=title,
        subject=(data.get("subject") or "").strip(),
        description=(data.get("description") or "").strip(),
        teacher_id=g.user.id,
        join_code=secrets.token_hex(4).upper()
    )
    db.session.add(classroom)
    db.session.commit()
    return jsonify(classroom={
        "id": classroom.id, "title": classroom.title, "subject": classroom.subject,
        "description": classroom.description, "join_code": classroom.join_code
    }), 201

@app.post("/api/classrooms/join")
@auth_required
def join_classroom():
    if g.user.role != "student":
        return jsonify(error="Only student accounts can request to join."), 403
    data = request.get_json(silent=True) or {}
    code = (data.get("join_code") or "").strip().upper()
    classroom = Classroom.query.filter_by(join_code=code).first()
    if not classroom:
        return jsonify(error="Classroom code not found."), 404
    existing = Membership.query.filter_by(classroom_id=classroom.id, student_id=g.user.id).first()
    if existing:
        return jsonify(message="Request already exists.", status=existing.status)
    membership = Membership(classroom_id=classroom.id, student_id=g.user.id)
    db.session.add(membership)
    db.session.commit()
    return jsonify(message="Join request sent to teacher.", status="pending"), 201

@app.get("/api/classrooms")
@auth_required
def list_classrooms():
    if g.user.role == "teacher":
        rooms = Classroom.query.filter_by(teacher_id=g.user.id).all()
    else:
        memberships = Membership.query.filter_by(student_id=g.user.id, status="approved").all()
        room_ids = [m.classroom_id for m in memberships]
        rooms = Classroom.query.filter(Classroom.id.in_(room_ids)).all() if room_ids else []
    return jsonify(classrooms=[{
        "id": r.id, "title": r.title, "subject": r.subject,
        "description": r.description, "join_code": r.join_code if r.teacher_id == g.user.id else None
    } for r in rooms])

@app.get("/api/classrooms/<int:classroom_id>/requests")
@auth_required
def join_requests(classroom_id):
    room = db.session.get(Classroom, classroom_id)
    if not room or room.teacher_id != g.user.id:
        return jsonify(error="Classroom not found or access denied."), 404
    requests_list = Membership.query.filter_by(classroom_id=room.id, status="pending").all()
    return jsonify(requests=[{
        "membership_id": m.id, "student": user_data(db.session.get(User, m.student_id))
    } for m in requests_list])

@app.post("/api/memberships/<int:membership_id>/approve")
@auth_required
def approve_membership(membership_id):
    membership = db.session.get(Membership, membership_id)
    room = db.session.get(Classroom, membership.classroom_id) if membership else None
    if not membership or not room or room.teacher_id != g.user.id:
        return jsonify(error="Request not found or access denied."), 404
    membership.status = "approved"
    db.session.commit()
    return jsonify(message="Student approved.")

@app.post("/api/classrooms/<int:classroom_id>/lessons")
@auth_required
def add_lesson(classroom_id):
    room = db.session.get(Classroom, classroom_id)
    if not room or room.teacher_id != g.user.id:
        return jsonify(error="Classroom not found or access denied."), 404
    data = request.get_json(silent=True) or {}
    title, video_url = (data.get("title") or "").strip(), (data.get("video_url") or "").strip()
    if not title or not video_url:
        return jsonify(error="Lesson title and video URL are required."), 400
    lesson = Lesson(classroom_id=room.id, title=title, video_url=video_url, notes=(data.get("notes") or "").strip())
    db.session.add(lesson)
    db.session.commit()
    return jsonify(message="Lesson added.", lesson={"id": lesson.id, "title": lesson.title, "video_url": lesson.video_url, "notes": lesson.notes}), 201

@app.get("/api/classrooms/<int:classroom_id>/lessons")
@auth_required
def get_lessons(classroom_id):
    room = db.session.get(Classroom, classroom_id)
    if not room:
        return jsonify(error="Classroom not found."), 404
    allowed = room.teacher_id == g.user.id or Membership.query.filter_by(
        classroom_id=room.id, student_id=g.user.id, status="approved"
    ).first()
    if not allowed:
        return jsonify(error="You are not approved for this classroom."), 403
    lessons = Lesson.query.filter_by(classroom_id=room.id).order_by(Lesson.created_at.desc()).all()
    return jsonify(lessons=[{"id": x.id, "title": x.title, "video_url": x.video_url, "notes": x.notes} for x in lessons])

@app.get("/api/dashboard")
@auth_required
def dashboard():
    if g.user.role == "teacher":
        rooms = Classroom.query.filter_by(teacher_id=g.user.id).all()
        room_ids = [r.id for r in rooms]
        pending = Membership.query.filter(Membership.classroom_id.in_(room_ids), Membership.status == "pending").count() if room_ids else 0
        return jsonify(role="teacher", classrooms=len(rooms), pending_requests=pending)
    approved = Membership.query.filter_by(student_id=g.user.id, status="approved").count()
    pending = Membership.query.filter_by(student_id=g.user.id, status="pending").count()
    return jsonify(role="student", joined_classrooms=approved, pending_requests=pending)

@app.errorhandler(404)
def not_found(_):
    return jsonify(error="Route not found."), 404

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
