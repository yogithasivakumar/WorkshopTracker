from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from bson.objectid import ObjectId
import os
from datetime import datetime
import io
from reportlab.pdfgen import canvas
import qrcode
import base64
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")

    app.config["MONGO_URI"] = os.environ.get("MONGO_URI", "mongodb://localhost:27017/workshop_db")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

    if test_config:
        app.config.update(test_config)

    client = MongoClient(app.config["MONGO_URI"])
    db = client.get_database()
    app.db = db

    def login_required(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "username" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated_function

    def role_required(role):
        from functools import wraps
        def decorator(f):
            @wraps(f)
            def wrapped(*args, **kwargs):
                if "role" not in session or session["role"] != role:
                    flash("You don't have access to this page.", "danger")
                    return redirect(url_for("dashboard"))
                return f(*args, **kwargs)
            return wrapped
        return decorator

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            username = request.form["username"]
            email = request.form["email"]
            password = request.form["password"]
            role = request.form["role"]

            if app.db.users.find_one({"username": username}):
                flash("Username already exists!", "danger")
                return redirect(url_for("signup"))

            hashed_pw = generate_password_hash(password)
            app.db.users.insert_one({
                "username": username,
                "email": email,
                "password": hashed_pw,
                "role": role
            })
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]

            user = app.db.users.find_one({"username": username})
            if user and check_password_hash(user["password"], password):
                session["user_id"] = str(user["_id"])
                session["username"] = user["username"]
                session["role"] = user["role"]
                flash("Logged in successfully!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid username or password", "danger")

        return render_template("login.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        role = session.get("role")
        if role == "organizer":
            workshops = list(app.db.workshops.find({"organizer_id": ObjectId(session["user_id"])}))
            for w in workshops:
                w["_id"] = str(w["_id"])
            return render_template("dashboard_organizer.html", username=session["username"], workshops=workshops)
        else:
            return render_template("dashboard_participant.html", username=session["username"])

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Logged out successfully!", "info")
        return redirect(url_for("index"))

    # ------------- PHASE 3 ROUTES -----------------

    # Organizer: Create workshop
    @app.route("/workshops/create", methods=["GET", "POST"])
    @login_required
    @role_required("organizer")
    def create_workshop():
        if request.method == "POST":
            title = request.form["title"]
            description = request.form["description"]
            date_str = request.form["date"]
            capacity = int(request.form["capacity"])

            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                flash("Invalid date format. Use YYYY-MM-DD.", "danger")
                return redirect(url_for("create_workshop"))

            workshop = {
                "title": title,
                "description": description,
                "date": date,
                "capacity": capacity,
                "organizer_id": ObjectId(session["user_id"]),
                "created_at": datetime.utcnow()
            }
            app.db.workshops.insert_one(workshop)
            flash("Workshop created successfully!", "success")
            return redirect(url_for("dashboard"))

        return render_template("create_workshop.html")

    # View all workshops (participant and organizer)
    @app.route("/workshops")
    @login_required
    def list_workshops():
        workshops = list(app.db.workshops.find().sort("date", 1))
        for w in workshops:
            w["_id"] = str(w["_id"])
        return render_template("list_workshops.html", workshops=workshops)

    # Participant: Register to workshop
    @app.route("/workshops/register/<workshop_id>")
    @login_required
    @role_required("participant")
    def register_workshop(workshop_id):
        participant_id = ObjectId(session["user_id"])
        workshop = app.db.workshops.find_one({"_id": ObjectId(workshop_id)})
        if not workshop:
            flash("Workshop not found.", "danger")
            return redirect(url_for("list_workshops"))

        existing = app.db.registrations.find_one({
            "workshop_id": ObjectId(workshop_id),
            "participant_id": participant_id
        })
        if existing:
            flash("You are already registered for this workshop.", "info")
            return redirect(url_for("list_workshops"))

        reg_count = app.db.registrations.count_documents({"workshop_id": ObjectId(workshop_id)})
        if reg_count >= workshop["capacity"]:
            flash("Sorry, this workshop is full.", "danger")
            return redirect(url_for("list_workshops"))

        app.db.registrations.insert_one({
            "workshop_id": ObjectId(workshop_id),
            "participant_id": participant_id,
            "registered_at": datetime.utcnow(),
            "status": "registered"
        })
        flash("Registered successfully!", "success")
        return redirect(url_for("list_workshops"))

    # Organizer: View registrations for their workshops
    @app.route("/workshops/registrations")
    @login_required
    @role_required("organizer")
    def view_registrations():
        organizer_id = ObjectId(session["user_id"])

        workshops = list(app.db.workshops.find({"organizer_id": organizer_id}))
        workshop_ids = [w["_id"] for w in workshops]

        registrations = list(app.db.registrations.find({"workshop_id": {"$in": workshop_ids}}))

        for reg in registrations:
            participant = app.db.users.find_one({"_id": reg["participant_id"]}, {"password": 0})
            workshop = next((w for w in workshops if w["_id"] == reg["workshop_id"]), None)
            reg["participant"] = participant
            reg["workshop"] = workshop
            reg["_id"] = str(reg["_id"])
            if participant:
                reg["participant"]["_id"] = str(participant["_id"])
            if workshop:
                reg["workshop"]["_id"] = str(workshop["_id"])

        return render_template("view_registrations.html", registrations=registrations)

    # Organizer: View attendance for their workshops
    @app.route("/workshops/attendance")
    @login_required
    @role_required("organizer")
    def view_attendance():
        organizer_id = ObjectId(session["user_id"])

        workshops = list(app.db.workshops.find({"organizer_id": organizer_id}))
        workshop_ids = [w["_id"] for w in workshops]

        attendance_records = list(app.db.attendance.find({"workshop_id": {"$in": workshop_ids}}).sort([("date", 1)]))

        for record in attendance_records:
            participant = app.db.users.find_one({"_id": record["participant_id"]}, {"password": 0})
            workshop = next((w for w in workshops if w["_id"] == record["workshop_id"]), None)

            record["participant"] = participant
            record["workshop"] = workshop
            record["_id"] = str(record["_id"])
            if participant:
                record["participant"]["_id"] = str(participant["_id"])
            if workshop:
                record["workshop"]["_id"] = str(workshop["_id"])

        return render_template("view_attendance.html", attendance_records=attendance_records)

    # Organizer: Mark attendance for a workshop manually (optional)
    @app.route("/workshops/<workshop_id>/attendance/mark", methods=["GET", "POST"])
    @login_required
    @role_required("organizer")
    def mark_attendance(workshop_id):
        organizer_id = ObjectId(session["user_id"])
        workshop = app.db.workshops.find_one({"_id": ObjectId(workshop_id), "organizer_id": organizer_id})
        if not workshop:
            flash("Workshop not found or access denied.", "danger")
            return redirect(url_for("dashboard"))

        registrations = list(app.db.registrations.find({"workshop_id": ObjectId(workshop_id)}))
        for reg in registrations:
            reg["_id"] = str(reg["_id"])
            participant = app.db.users.find_one({"_id": reg["participant_id"]}, {"password": 0})
            reg["participant"] = participant

        if request.method == "POST":
            attendance_ids = request.form.getlist("attendance")  # list of registration _id's marked present
            for reg in registrations:
                attended = reg["_id"] in attendance_ids
                existing_attendance = app.db.attendance.find_one({
                    "workshop_id": ObjectId(workshop_id),
                    "participant_id": reg["participant_id"],
                    "date": workshop["date"]
                })
                if existing_attendance:
                    app.db.attendance.update_one(
                        {"_id": existing_attendance["_id"]},
                        {"$set": {
                            "status": "present" if attended else "absent",
                            "date": workshop["date"]
                        }}
                    )
                else:
                    app.db.attendance.insert_one({
                        "workshop_id": ObjectId(workshop_id),
                        "participant_id": reg["participant_id"],
                        "status": "present" if attended else "absent",
                        "date": workshop["date"]
                    })
            flash("Attendance updated successfully!", "success")
            return redirect(url_for("view_attendance"))

        return render_template("mark_attendance.html", workshop=workshop, registrations=registrations)

    # ---------------- QR CODE ATTENDANCE FEATURE -----------------

    @app.route("/workshops/<workshop_id>/attendance/qrcode")
    @login_required
    @role_required("organizer")
    def generate_qr_code(workshop_id):
        organizer_id = ObjectId(session["user_id"])
        workshop = app.db.workshops.find_one({"_id": ObjectId(workshop_id), "organizer_id": organizer_id})
        if not workshop:
            flash("Workshop not found or access denied.", "danger")
            return redirect(url_for("dashboard"))

        date_str = workshop["date"].strftime("%Y-%m-%d")
        scan_url = url_for("scan_attendance", workshop_id=workshop_id, date=date_str, _external=True)

        qr = qrcode.make(scan_url)
        buffered = io.BytesIO()
        qr.save(buffered, format="PNG")
        qr_b64 = base64.b64encode(buffered.getvalue()).decode()

        return render_template("show_qr_code.html", qr_code=qr_b64, scan_url=scan_url, workshop=workshop)

    @app.route("/workshops/<workshop_id>/attendance/scan/<date>")
    @login_required
    @role_required("participant")
    def scan_attendance(workshop_id, date):
        participant_id = ObjectId(session["user_id"])

        workshop = app.db.workshops.find_one({"_id": ObjectId(workshop_id)})
        if not workshop:
            flash("Workshop not found.", "danger")
            return redirect(url_for("participant_workshops"))

        registration = app.db.registrations.find_one({
            "workshop_id": ObjectId(workshop_id),
            "participant_id": participant_id
        })
        if not registration:
            flash("You are not registered for this workshop.", "danger")
            return redirect(url_for("participant_workshops"))

        attendance = app.db.attendance.find_one({
            "workshop_id": ObjectId(workshop_id),
            "participant_id": participant_id,
            "date": date
        })
        if attendance:
            flash("Attendance already marked for this session.", "info")
        else:
            app.db.attendance.insert_one({
                "workshop_id": ObjectId(workshop_id),
                "participant_id": participant_id,
                "date": date,
                "marked_at": datetime.utcnow(),
                "status": "present"
            })
            flash("Attendance marked successfully!", "success")

        return redirect(url_for("participant_workshops"))

    # Participant: View available workshops
    @app.route("/participant/workshops")
    @login_required
    @role_required("participant")
    def participant_workshops():
        workshops = list(app.db.workshops.find().sort("date", 1))
        for w in workshops:
            w["_id"] = str(w["_id"])
        return render_template("participant_workshops.html", workshops=workshops)

    # Participant: View their attendance
    @app.route("/participant/attendance")
    @login_required
    @role_required("participant")
    def participant_attendance():
        participant_id = ObjectId(session["user_id"])

        attendance_records = list(app.db.attendance.find({"participant_id": participant_id}).sort([("date", 1)]))

        for record in attendance_records:
            workshop = app.db.workshops.find_one({"_id": record["workshop_id"]})
            record["workshop"] = workshop
            record["_id"] = str(record["_id"])
            if workshop:
                record["workshop"]["_id"] = str(workshop["_id"])

        return render_template("participant_attendance.html", attendance_records=attendance_records)

    # Participant: Certificates page - show attended workshops with download links
    @app.route("/participant/certificates")
    @login_required
    @role_required("participant")
    def participant_certificates():
        participant_id = ObjectId(session["user_id"])

        attendance_records = list(app.db.attendance.find({
            "participant_id": participant_id,
            "status": "present"
        }))

        for record in attendance_records:
            workshop = app.db.workshops.find_one({"_id": record["workshop_id"]})
            record["workshop"] = workshop
            record["_id"] = str(record["_id"])
            if workshop:
                record["workshop"]["_id"] = str(workshop["_id"])

        return render_template("participant_certificates.html", attendance_records=attendance_records)

    # Participant: Download certificate PDF
    @app.route("/participant/certificate/download/<workshop_id>")
    @login_required
    @role_required("participant")
    def download_certificate(workshop_id):
        participant_id = ObjectId(session["user_id"])

        attendance = app.db.attendance.find_one({
            "workshop_id": ObjectId(workshop_id),
            "participant_id": participant_id,
            "status": "present"
        })

        if not attendance:
            flash("Certificate unavailable: Attendance not marked as present.", "danger")
            return redirect(url_for("participant_certificates"))

        workshop = app.db.workshops.find_one({"_id": ObjectId(workshop_id)})

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer)
        c.setFont("Helvetica", 20)
        c.drawString(100, 750, "Certificate of Completion")
        c.setFont("Helvetica", 14)
        c.drawString(100, 700, f"This certifies that {session['username']}")
        c.drawString(100, 670, f"has attended the workshop:")
        c.setFont("Helvetica-Bold", 16)
        c.drawString(100, 640, workshop["title"])
        c.setFont("Helvetica", 12)
        c.drawString(100, 600, f"Date: {workshop['date'].strftime('%Y-%m-%d')}")
        c.showPage()
        c.save()
        buffer.seek(0)

        return send_file(buffer, as_attachment=True, download_name=f"Certificate_{workshop['title']}.pdf", mimetype='application/pdf')

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
