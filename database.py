
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_FILE = DATABASE_DIR / "portal.db"

DATABASE_DIR.mkdir(exist_ok=True)


def get_db_connection():
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
            registration_number TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            deadline TEXT NOT NULL,
            max_marks INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by)
                REFERENCES users(user_id)
                ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            file_name TEXT NOT NULL DEFAULT 'URL Submission',
            file_path TEXT NOT NULL DEFAULT '',
            submission_url TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            submission_status TEXT NOT NULL DEFAULT 'SUBMITTED',
            marks INTEGER,
            feedback TEXT,
            graded_at TIMESTAMP,
            FOREIGN KEY (assignment_id)
                REFERENCES assignments(assignment_id)
                ON DELETE CASCADE,
            FOREIGN KEY (student_id)
                REFERENCES users(user_id)
                ON DELETE CASCADE
        )
    """)

    # Safely add columns to an existing database
    user_columns = {
        row["name"]
        for row in cursor.execute("PRAGMA table_info(users)").fetchall()
    }

    if "registration_number" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN registration_number TEXT"
        )

    submission_columns = {
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(submissions)"
        ).fetchall()
    }

    if "submission_url" not in submission_columns:
        cursor.execute(
            "ALTER TABLE submissions ADD COLUMN submission_url TEXT"
        )

    # Demo teacher
    teacher = cursor.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("teacher@example.com",)
    ).fetchone()

    if teacher is None:
        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            "Demo Teacher",
            "teacher@example.com",
            generate_password_hash("teacher123"),
            "teacher"
        ))

    # Demo student
    student = cursor.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("student@example.com",)
    ).fetchone()

    if student is None:
        cursor.execute("""
            INSERT INTO users
            (name, email, password, role, registration_number)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "Demo Student",
            "student@example.com",
            generate_password_hash("student123"),
            "student",
            "DEMO-001"
        ))

    connection.commit()
    connection.close()


if __name__ == "__main__":
    init_database()
    print("Database initialized successfully.")
