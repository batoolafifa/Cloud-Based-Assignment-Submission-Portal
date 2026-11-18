import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from database import get_db_connection, init_database


# --------------------------------------------------
# Configuration
# --------------------------------------------------

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"

UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt"
}

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "development-secret-key"
)

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def login_required():
    return "user_id" in session


def teacher_required():
    return (
        "user_id" in session
        and session.get("role") == "teacher"
    )


def student_required():
    return (
        "user_id" in session
        and session.get("role") == "student"
    )


# --------------------------------------------------
# Home
# --------------------------------------------------

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") == "teacher":
        return redirect(url_for("teacher_dashboard"))

    return redirect(url_for("student_dashboard"))


# --------------------------------------------------
# Register
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])

def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        registration_number = request.form.get(
            "registration_number", ""
        ).strip()

        if not name or not email or not password or not role:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("register"))

        if role not in ["student", "teacher"]:
            flash("Invalid role selected.", "error")
            return redirect(url_for("register"))

        if role == "student" and not registration_number:
            flash("Registration number is required.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
            return redirect(url_for("register"))

        connection = get_db_connection()

        existing_user = connection.execute(
            "SELECT user_id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            connection.close()
            flash("Email already registered.", "error")
            return redirect(url_for("register"))

        if registration_number:
            existing_reg = connection.execute(
                "SELECT user_id FROM users WHERE registration_number = ?",
                (registration_number,)
            ).fetchone()

            if existing_reg:
                connection.close()
                flash("Registration number already registered.", "error")
                return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        connection.execute("""
            INSERT INTO users
            (name, email, password, role, registration_number)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            email,
            hashed_password,
            role,
            registration_number if role == "student" else None
        ))

        connection.commit()
        connection.close()

        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")



# --------------------------------------------------
# Login
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()

        user = connection.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email,)).fetchone()

        connection.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["user_id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            flash("Login successful.", "success")

            if user["role"] == "teacher":
                return redirect(url_for("teacher_dashboard"))

            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


# --------------------------------------------------
# Logout
# --------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


# --------------------------------------------------
# Student Dashboard
# --------------------------------------------------

@app.route("/student/dashboard")
def student_dashboard():

    if not student_required():
        flash("Student access required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()

    assignments = connection.execute("""
        SELECT
            a.*,
            u.name AS teacher_name,
            s.submission_id,
            s.submission_status,
            s.marks,
            s.feedback,
            s.submitted_at
        FROM assignments a
        JOIN users u
            ON a.created_by = u.user_id
        LEFT JOIN submissions s
            ON a.assignment_id = s.assignment_id
            AND s.student_id = ?
        ORDER BY a.deadline ASC
    """, (session["user_id"],)).fetchall()

    total_assignments = connection.execute("""
        SELECT COUNT(*) AS count
        FROM assignments
    """).fetchone()["count"]

    submitted_assignments = connection.execute("""
        SELECT COUNT(*) AS count
        FROM submissions
        WHERE student_id = ?
    """, (session["user_id"],)).fetchone()["count"]

    graded_assignments = connection.execute("""
        SELECT COUNT(*) AS count
        FROM submissions
        WHERE student_id = ?
        AND marks IS NOT NULL
    """, (session["user_id"],)).fetchone()["count"]

    connection.close()

    pending_assignments = (
        total_assignments - submitted_assignments
    )

    return render_template(
        "student_dashboard.html",
        assignments=assignments,
        total_assignments=total_assignments,
        submitted_assignments=submitted_assignments,
        pending_assignments=pending_assignments,
        graded_assignments=graded_assignments
    )


# --------------------------------------------------
# Teacher Dashboard
# --------------------------------------------------

@app.route("/teacher/dashboard")
def teacher_dashboard():

    if not teacher_required():
        flash("Teacher access required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()

    assignments = connection.execute("""
        SELECT
            a.*,
            COUNT(s.submission_id) AS submission_count
        FROM assignments a
        LEFT JOIN submissions s
            ON a.assignment_id = s.assignment_id
        WHERE a.created_by = ?
        GROUP BY a.assignment_id
        ORDER BY a.deadline ASC
    """, (session["user_id"],)).fetchall()

    total_assignments = connection.execute("""
        SELECT COUNT(*) AS count
        FROM assignments
        WHERE created_by = ?
    """, (session["user_id"],)).fetchone()["count"]

    total_submissions = connection.execute("""
        SELECT COUNT(*) AS count
        FROM submissions s
        JOIN assignments a
            ON s.assignment_id = a.assignment_id
        WHERE a.created_by = ?
    """, (session["user_id"],)).fetchone()["count"]

    pending_reviews = connection.execute("""
        SELECT COUNT(*) AS count
        FROM submissions s
        JOIN assignments a
            ON s.assignment_id = a.assignment_id
        WHERE a.created_by = ?
        AND s.marks IS NULL
    """, (session["user_id"],)).fetchone()["count"]

    total_students = connection.execute("""
        SELECT COUNT(*) AS count
        FROM users
        WHERE role = 'student'
    """).fetchone()["count"]

    connection.close()

    return render_template(
        "teacher_dashboard.html",
        assignments=assignments,
        total_assignments=total_assignments,
        total_submissions=total_submissions,
        pending_reviews=pending_reviews,
        total_students=total_students
    )


# --------------------------------------------------
# Create Assignment
# --------------------------------------------------

@app.route("/teacher/create-assignment", methods=["GET", "POST"])
def create_assignment():

    if not teacher_required():
        flash("Teacher access required.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline = request.form.get("deadline", "").strip()
        max_marks = request.form.get("max_marks", "").strip()

        if not title or not deadline or not max_marks:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("create_assignment"))

        try:
            max_marks = int(max_marks)

            if max_marks <= 0:
                raise ValueError

        except ValueError:
            flash("Maximum marks must be a positive number.", "error")
            return redirect(url_for("create_assignment"))

        connection = get_db_connection()

        connection.execute("""
            INSERT INTO assignments
            (title, description, deadline, max_marks, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (
            title,
            description,
            deadline,
            max_marks,
            session["user_id"]
        ))

        connection.commit()
        connection.close()

        flash(
            "Assignment created successfully.",
            "success"
        )

        return redirect(url_for("teacher_dashboard"))

    return render_template("create_assignment.html")


# --------------------------------------------------
# Assignment Details
# --------------------------------------------------

@app.route("/assignment/<int:assignment_id>")
def assignment_details(assignment_id):

    if not login_required():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()

    assignment = connection.execute("""
        SELECT
            a.*,
            u.name AS teacher_name
        FROM assignments a
        JOIN users u
            ON a.created_by = u.user_id
        WHERE a.assignment_id = ?
    """, (assignment_id,)).fetchone()

    if not assignment:
        connection.close()
        flash("Assignment not found.", "error")
        return redirect(url_for("home"))

    submission = None

    if session["role"] == "student":

        submission = connection.execute("""
            SELECT *
            FROM submissions
            WHERE assignment_id = ?
            AND student_id = ?
            ORDER BY submitted_at DESC
            LIMIT 1
        """, (
            assignment_id,
            session["user_id"]
        )).fetchone()

    connection.close()

    return render_template(
        "assignment_details.html",
        assignment=assignment,
        submission=submission
    )


# --------------------------------------------------
# Submit Assignment
# --------------------------------------------------


@app.route(
    "/student/assignment/<int:assignment_id>/submit",
    methods=["GET", "POST"]
)
def submit_assignment(assignment_id):

    if not student_required():
        flash("Student access required.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()

    assignment = connection.execute("""
        SELECT *
        FROM assignments
        WHERE assignment_id = ?
    """, (assignment_id,)).fetchone()

    if not assignment:
        connection.close()
        flash("Assignment not found.", "error")
        return redirect(url_for("student_dashboard"))

    existing_submission = connection.execute("""
        SELECT *
        FROM submissions
        WHERE assignment_id = ?
        AND student_id = ?
        ORDER BY submitted_at DESC
        LIMIT 1
    """, (assignment_id, session["user_id"])).fetchone()

    if request.method == "POST":

        submission_url = request.form.get(
            "submission_url", ""
        ).strip()

        if not submission_url:
            connection.close()
            flash("Submission URL is required.", "error")
            return redirect(request.url)

        from urllib.parse import urlparse

        parsed_url = urlparse(submission_url)

        if (
            parsed_url.scheme not in ("http", "https")
            or not parsed_url.netloc
            or "." not in parsed_url.netloc
        ):
            connection.close()
            flash("Please enter a valid URL.", "error")
            return redirect(request.url)

        submitted_at = datetime.now()

        deadline = datetime.fromisoformat(assignment["deadline"])

        status = (
            "SUBMITTED"
            if submitted_at <= deadline
            else "LATE"
        )

        if existing_submission:
            connection.execute("""
                UPDATE submissions
                SET
                    submission_url = ?,
                    submitted_at = ?,
                    submission_status = ?,
                    marks = NULL,
                    feedback = NULL,
                    graded_at = NULL
                WHERE submission_id = ?
            """, (
                submission_url,
                submitted_at.strftime("%Y-%m-%d %H:%M:%S"),
                status,
                existing_submission["submission_id"]
            ))

        else:
            connection.execute("""
                INSERT INTO submissions
                (
                    assignment_id,
                    student_id,
                    file_name,
                    file_path,
                    submission_url,
                    submitted_at,
                    submission_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                assignment_id,
                session["user_id"],
                "URL Submission",
                "",
                submission_url,
                submitted_at.strftime("%Y-%m-%d %H:%M:%S"),
                status
            ))

        connection.commit()
        connection.close()

        flash("Assignment submitted successfully.", "success")

        return redirect(
            url_for(
                "assignment_details",
                assignment_id=assignment_id
            )
        )

    connection.close()

    return render_template(
        "submit_assignment.html",
        assignment=assignment,
        existing_submission=existing_submission
    )


# --------------------------------------------------
# Teacher: View Submissions
# --------------------------------------------------



# --------------------------------------------------
# Grade Submission
# --------------------------------------------------

@app.route(
    "/teacher/submission/<int:submission_id>/grade",
    methods=["POST"]
)
def grade_submission(submission_id):

    if not teacher_required():
        flash("Teacher access required.", "error")
        return redirect(url_for("login"))

    marks = request.form.get("marks", "").strip()
    feedback = request.form.get("feedback", "").strip()

    try:
        marks = int(marks)
    except ValueError:
        flash("Marks must be a valid number.", "error")
        return redirect(url_for("teacher_dashboard"))

    connection = get_db_connection()

    submission = connection.execute("""
        SELECT
            s.*,
            a.max_marks,
            a.created_by,
            a.assignment_id
        FROM submissions s
        JOIN assignments a
            ON s.assignment_id = a.assignment_id
        WHERE s.submission_id = ?
    """, (submission_id,)).fetchone()

    if not submission:

        connection.close()

        flash(
            "Submission not found.",
            "error"
        )

        return redirect(url_for("teacher_dashboard"))

    if submission["created_by"] != session["user_id"]:

        connection.close()

        flash(
            "You are not authorized to grade this submission.",
            "error"
        )

        return redirect(url_for("teacher_dashboard"))

    if marks < 0 or marks > submission["max_marks"]:

        connection.close()

        flash(
            f"Marks must be between 0 and "
            f"{submission['max_marks']}.",
            "error"
        )

        return redirect(
            url_for(
                "view_submissions",
                assignment_id=submission["assignment_id"]
            )
        )

    connection.execute("""
        UPDATE submissions
        SET
            marks = ?,
            feedback = ?,
            graded_at = ?
        WHERE submission_id = ?
    """, (
        marks,
        feedback,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        submission_id
    ))

    connection.commit()
    connection.close()

    flash(
        "Marks and feedback saved successfully.",
        "success"
    )

    return redirect(
        url_for(
            "view_submissions",
            assignment_id=submission["assignment_id"]
        )
    )


# --------------------------------------------------
# Download Submission
# --------------------------------------------------

@app.route(
    "/download/<int:submission_id>"
)
def download_submission(submission_id):

    if not login_required():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    connection = get_db_connection()

    submission = connection.execute("""
        SELECT
            s.*,
            a.created_by
        FROM submissions s
        JOIN assignments a
            ON s.assignment_id = a.assignment_id
        WHERE s.submission_id = ?
    """, (submission_id,)).fetchone()

    connection.close()

    if not submission:
        flash("Submission not found.", "error")
        return redirect(url_for("home"))

    # Student can download only their own file
    if session["role"] == "student":

        if submission["student_id"] != session["user_id"]:
            flash(
                "You are not authorized to access this file.",
                "error"
            )
            return redirect(url_for("student_dashboard"))

    # Teacher can download submissions for assignments they created
    elif session["role"] == "teacher":

        if submission["created_by"] != session["user_id"]:
            flash(
                "You are not authorized to access this file.",
                "error"
            )
            return redirect(url_for("teacher_dashboard"))

    else:
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        submission["file_path"],
        as_attachment=True,
        download_name=submission["file_name"]
    )


# --------------------------------------------------
# Error Handling
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. Maximum size is 5 MB.",
        "error"
    )

    return redirect(url_for("student_dashboard"))


# --------------------------------------------------
# Start Application
# --------------------------------------------------

if __name__ == "__main__":

    init_database()

    print("=" * 50)
    print("Cloud Assignment Submission Portal")
    print("=" * 50)
    print("Application running at:")
    print("http://127.0.0.1:5000")
    print("=" * 50)

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )