
import json
import os
import sys
import unittest
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class ReportResult(unittest.TextTestResult):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_details = []
        self.passed_count = 0

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_count += 1
        self.test_details.append({
            "name": test.id(),
            "result": "passed",
            "failure_message": None
        })

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.test_details.append({
            "name": test.id(),
            "result": "failed",
            "failure_message": self._exc_info_to_string(err, test)
        })

    def addError(self, test, err):
        super().addError(test, err)
        self.test_details.append({
            "name": test.id(),
            "result": "error",
            "failure_message": self._exc_info_to_string(err, test)
        })


def main():

    suite = unittest.defaultTestLoader.discover("tests")

    runner = unittest.TextTestRunner(
        verbosity=2,
        resultclass=ReportResult
    )

    result = runner.run(suite)

    failed = len(result.failures) + len(result.errors)

    report = {
        "repository": os.getenv("GITHUB_REPOSITORY", "local"),
        "branch": os.getenv("GITHUB_REF_NAME", "local"),
        "commit_sha": os.getenv("GITHUB_SHA", "local"),
        "pipeline_run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "execution_timestamp": datetime.now(timezone.utc).isoformat(),
        "tests": result.test_details,
        "total_tests": result.testsRun,
        "passed": result.passed_count,
        "failed": failed,
        "overall_status": "passed" if result.wasSuccessful() else "failed"
    }

    Path("test-report.json").write_text(
        json.dumps(report, indent=4),
        encoding="utf-8"
    )

    print("\nTest report created successfully.")

    receiver_url = os.getenv("REPORT_RECEIVER_URL")
    token = os.getenv("REPORT_TOKEN")

    if receiver_url and token:

        request = urllib.request.Request(
            receiver_url.rstrip("/") + "/receive-report",
            data=json.dumps(report).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Report-Token": token
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                print("Report delivery successful:")
                print(response.read().decode("utf-8"))

        except Exception as error:
            print("Report delivery failed:", error)
            sys.exit(2)

    else:
        print("Report receiver settings are missing.")
        sys.exit(2)

    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
