from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO, join_room, emit
from pathlib import Path
from datetime import datetime
import base64
import logging

# ---------------------------
# Configuration
# ---------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "replace-with-a-secure-secret"
socketio = SocketIO(app, cors_allowed_origins="*")

BASE = Path(__file__).parent.resolve()
LOGFILE = BASE / "log.txt"
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)

# simple in-memory store (persist only while process is running)
clients = {}  # client_id -> { lat, lon, last_seen, path, last_image, consent }

# set up logging to file
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def log_line(line: str):
    try:
        with LOGFILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        logging.exception("Failed to write log")


# ---------------------------
# Routes
# ---------------------------
@app.route("/")
def index():
    # renders templates/index.html
    return render_template("index.html")


@app.route("/admin")
def admin():
    # renders templates/admin.html
    return render_template("admin.html")


@app.route("/images")
def list_images():
    """Return list of files inside static/img (useful for user to view available images)."""
    img_dir = Path(app.static_folder) / "img"
    if not img_dir.exists():
        return jsonify({"images": []})
    files = [
        f.name
        for f in img_dir.iterdir()
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")
    ]
    return jsonify({"images": files})


@app.route("/consent", methods=["POST"])
def consent():
    """
    Record user's consent choices.

    Body JSON:
    { client_id, share_location: bool, share_camera: bool, share_notifications: bool }
    """
    data = request.get_json(force=True, silent=True) or {}
    client_id = data.get("client_id")
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400

    rec = clients.get(client_id, {"path": []})
    rec["consent"] = {
        "share_location": bool(data.get("share_location")),
        "share_camera": bool(data.get("share_camera")),
        "share_notifications": bool(data.get("share_notifications")),
        "ts": datetime.utcnow().isoformat(),
    }
    clients[client_id] = rec
    log_line(
        f"{rec['consent']['ts']} CONSENT client={client_id} loc={rec['consent']['share_location']} cam={rec['consent']['share_camera']}"
    )
    return jsonify({"status": "ok"})


@app.route("/report", methods=["POST"])
def report():
    """
    Client posts location:

    Body JSON:
    { client_id, latitude, longitude }
    """
    data = request.get_json(force=True, silent=True) or {}
    client_id = data.get("client_id")
    lat = data.get("latitude")
    lon = data.get("longitude")

    if not client_id or lat is None or lon is None:
        return jsonify({"error": "Missing fields"}), 400

    ts = datetime.utcnow().isoformat()
    rec = clients.get(client_id, {"path": []})
    try:
        rec.update({"lat": float(lat), "lon": float(lon), "last_seen": ts})
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid lat/lon"}), 400

    rec.setdefault("path", []).append([float(lat), float(lon)])
    clients[client_id] = rec

    log_line(f"{ts} REPORT client={client_id} lat={lat} lon={lon}")
    # broadcast to admins room
    socketio.emit(
        "location_update",
        {"client_id": client_id, "lat": rec["lat"], "lon": rec["lon"], "last_seen": ts},
        room="admins",
    )
    return jsonify({"status": "ok"})


@app.route("/capture", methods=["POST"])
def capture():
    """
    Accepts base64 dataURL image from client and stores it to uploads folder.

    Body JSON:
    { client_id, image: dataURL }
    """
    data = request.get_json(force=True, silent=True) or {}
    client_id = data.get("client_id")
    image_data = data.get("image")

    if not client_id or not image_data:
        return jsonify({"error": "Missing fields"}), 400

    if not isinstance(image_data, str) or not image_data.startswith("data:"):
        return jsonify({"error": "Invalid image format"}), 400

    try:
        header, b64 = image_data.split(",", 1)
    except ValueError:
        return jsonify({"error": "Bad image data"}), 400

    ext = "jpg" if ("jpeg" in header or "jpg" in header) else "png"
    try:
        img_bytes = base64.b64decode(b64)
    except Exception:
        return jsonify({"error": "Base64 decode error"}), 400

    filename = f"{client_id}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.{ext}"
    path = UPLOADS / filename
    try:
        path.write_bytes(img_bytes)
    except Exception:
        logging.exception("Failed to write upload file")
        return jsonify({"error": "Failed to save file"}), 500

    rec = clients.get(client_id, {"path": []})
    rec["last_image"] = filename
    rec["last_image_ts"] = datetime.utcnow().isoformat()
    clients[client_id] = rec

    log_line(f"{rec['last_image_ts']} CAPTURE client={client_id} file={filename}")
    # notify admins that an image was captured
    socketio.emit(
        "image_captured",
        {"client_id": client_id, "filename": filename, "ts": rec["last_image_ts"]},
        room="admins",
    )
    return jsonify({"status": "ok", "filename": filename})


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # serve uploaded captured images
    return send_from_directory(UPLOADS, filename)


@app.route("/clients")
def get_clients():
    # snapshot of clients (for admin initial load)
    return jsonify(clients)


# ---------------------------
# Socket.IO events
# ---------------------------
@socketio.on("register")
def handle_register(data):
    """
    data: { client_id, role }  role in ("client","admin")
    """
    client_id = (data or {}).get("client_id")
    role = (data or {}).get("role")

    if role == "admin":
        join_room("admins")
        # emit snapshot only to the connecting admin socket
        emit("clients_snapshot", clients, room=request.sid)
        logging.info("Admin joined admins room")
    elif role == "client" and client_id:
        join_room(client_id)
        emit("registered", {"status": "ok", "client_id": client_id}, room=request.sid)
        logging.info(f"Client {client_id} registered and joined its room")
    else:
        logging.info("Unknown register call: %s", data)


@socketio.on("stream_frame")
def handle_stream_frame(data):
    """
    forwarded streaming frames from client -> admins
    data: { client_id, image }
    """
    client_id = (data or {}).get("client_id")
    image = (data or {}).get("image")
    if not client_id or not image:
        return
    # forward to admins room (admins will display it)
    emit("stream_frame", {"client_id": client_id, "image": image}, room="admins", include_self=False)


@socketio.on("admin_send_notification")
def handle_admin_notification(data):
    """
    Admin requests a notification to a client.
    data: { client_id, message }
    """
    client_id = (data or {}).get("client_id")
    message = (data or {}).get("message")
    if not client_id or not message:
        return
    # emit notification to the client's room
    emit("notification", {"message": message, "ts": datetime.utcnow().isoformat()}, room=client_id)
    # ack to admins
    emit("notification_sent", {"client_id": client_id, "message": message}, room="admins")


# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    # For local development use. In production consider using eventlet/gevent worker if needed.
    logging.info("Starting Flask-SocketIO server")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
