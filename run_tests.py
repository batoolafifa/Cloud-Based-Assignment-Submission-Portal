
from flask import Flask, request, jsonify
from pathlib import Path
from datetime import datetime
import json
import os
import hmac

app = Flask(__name__)

REPORT_FILE = Path(__file__).resolve().parent / "test-report.json"


@app.route("/receive-report", methods=["POST"])
def receive_report():
    expected_token = os.getenv("REPORT_TOKEN")
    received_token = request.headers.get("X-Report-Token", "")

    if not expected_token:
        return jsonify({"error": "Receiver token is not configured"}), 503

    if not hmac.compare_digest(received_token, expected_token):
        return jsonify({"error": "Unauthorized"}), 401

    report = request.get_json(silent=True)

    if not isinstance(report, dict):
        return jsonify({"error": "Invalid report"}), 400

    report["received_at"] = datetime.now().isoformat(timespec="seconds")

    with open(REPORT_FILE, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    return jsonify({
        "message": "Test report received successfully",
        "file": str(REPORT_FILE)
    }), 200


if __name__ == "__main__":
    print("Local Report Receiver is running...")
    app.run(host="0.0.0.0", port=5001)
