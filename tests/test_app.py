
import unittest
import uuid
from datetime import datetime, timedelta

from app import app
from database import get_db_connection


class AssignmentPortalTests(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

        self.unique_id = uuid.uuid4().hex[:8]
        self.email = f"test_{self.unique_id}@example.com"
        self.registration_number = f"TEST-{self.unique_id}"

        connection = get_db_connection()

        cursor = connection.execute("""
            INSERT INTO users
            (name, email, password, role, registration_number)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "Test Student",
            self.email,
            "testpassword",
            "student",
            self.registration_number
        ))

        self.student_id = cursor.lastrowid

        cursor = connection.execute("""
            INSERT INTO users
            (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            "Test Teacher",
            f"teacher_{self.unique_id}@example.com",
            "testpassword",
            "teacher"
        ))

        self.teacher_id = cursor.lastrowid

        deadline = (
            datetime.now() + timedelta(days=7)
        ).isoformat(timespec="seconds")

        cursor = connection.execute("""
            INSERT INTO assignments
            (title, description, deadline, max_marks, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "Automated Test Assignment",
            "Testing URL submission",
            deadline,
            10,
            self.teacher_id
        ))

        self.assignment_id = cursor.lastrowid

        connection.commit()
        connection.close()

        with self.client.session_transaction() as session:
            session["user_id"] = self.student_id
            session["role"] = "student"

    def tearDown(self):
        connection = get_db_connection()

        connection.execute(
            "DELETE FROM assignments WHERE assignment_id = ?",
            (self.assignment_id,)
        )

        connection.execute(
            "DELETE FROM users WHERE user_id IN (?, ?)",
            (self.student_id, self.teacher_id)
        )

        connection.commit()
        connection.close()

    def test_valid_submission_is_saved_and_listed(self):
        url = "https://github.com/example"

        response = self.client.post(
            f"/student/assignment/{self.assignment_id}/submit",
            data={"submission_url": url},
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Assignment submitted successfully",
            response.data
        )

        connection = get_db_connection()

        submission = connection.execute("""
            SELECT submission_url
            FROM submissions
            WHERE assignment_id = ?
            AND student_id = ?
        """, (
            self.assignment_id,
            self.student_id
        )).fetchone()

        connection.close()

        self.assertIsNotNone(submission)
        self.assertEqual(submission["submission_url"], url)

        self.assertIn(url.encode(), response.data)

    def test_missing_registration_number_is_rejected(self):
        with self.client.session_transaction() as session:
            session.clear()

        response = self.client.post(
            "/register",
            data={
                "name": "Missing Registration",
                "email": f"missing_{self.unique_id}@example.com",
                "password": "password123",
                "role": "student",
                "registration_number": ""
            },
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Registration number is required",
            response.data
        )

    def test_invalid_url_is_rejected_and_not_saved(self):
        response = self.client.post(
            f"/student/assignment/{self.assignment_id}/submit",
            data={"submission_url": "not-a-valid-url"},
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Please enter a valid URL",
            response.data
        )

        connection = get_db_connection()

        submission = connection.execute("""
            SELECT submission_id
            FROM submissions
            WHERE assignment_id = ?
            AND student_id = ?
        """, (
            self.assignment_id,
            self.student_id
        )).fetchone()

        connection.close()

        self.assertIsNone(submission)


if __name__ == "__main__":
    unittest.main()
