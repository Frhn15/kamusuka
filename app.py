from flask import Flask, request, jsonify, render_template
from pathlib import Path
from datetime import datetime
import logging
import json

# --- setup ---
app = Flask(__name__, static_folder="static", template_folder="templates")

BASE = Path(__file__).parent.resolve()
LOGFILE = BASE / "reported_locations.log"
# logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def log_line(line: str):
    # write human-readable log line to file and logger
    try:
        with LOGFILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        logging.exception("Failed to append logfile")
    logging.info(line)

# --- routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/report", methods=["POST"])
def report():
    """
    Accept JSON:
    { "client_id": "...", "latitude":  -6.2, "longitude": 106.8, "source": "gps" }
    This endpoint records to server log and to reported_locations.log file.
    """
    data = request.get_json(force=True, silent=True) or {}
    client_id = data.get("client_id", "unknown")
    lat = data.get("latitude")
    lon = data.get("longitude")
    source = data.get("source", "unknown")

    if lat is None or lon is None:
        return jsonify({"error": "missing latitude/longitude"}), 400

    ts = datetime.utcnow().isoformat() + "Z"
    line = json.dumps({
        "ts": ts,
        "client_id": client_id,
        "latitude": float(lat),
        "longitude": float(lon),
        "source": source
    }, ensure_ascii=False)

    # write / log
    log_line(line)

    return jsonify({"status": "ok"}), 200

# --- run ---
if __name__ == "__main__":
    # For local testing
    logging.info("Starting server on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
