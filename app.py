from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from datetime import datetime
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

clients = {}
routes = {}

# -----------------------------
# Halaman utama dan admin
# -----------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

# -----------------------------
# Menerima data lokasi
# -----------------------------
@app.route('/report', methods=['POST'])
def report():
    """Menerima data lokasi & alamat dari client"""
    data = request.get_json()
    client_id = data.get('client_id')
    lat = float(data.get('latitude', 0))
    lon = float(data.get('longitude', 0))
    address = data.get('address', 'Alamat tidak diketahui')
    source = data.get('source', 'gps')

    if not client_id or not lat or not lon:
        return jsonify({"error": "data tidak valid"}), 400

    clients[client_id] = {
        "latitude": lat,
        "longitude": lon,
        "address": address,
        "source": source,
        "last_seen": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "last_image": clients.get(client_id, {}).get("last_image")
    }

    # simpan rute (track perjalanan)
    routes.setdefault(client_id, []).append({
        "lat": lat, "lon": lon, "time": datetime.now().isoformat()
    })

    # kirim update ke admin secara realtime
    socketio.emit('location_update', {
        "client_id": client_id,
        "latitude": lat,
        "longitude": lon,
        "address": address,
        "last_seen": clients[client_id]["last_seen"]
    })

    return jsonify({"status": "ok"})

# -----------------------------
# Upload gambar dari client
# -----------------------------
@app.route('/upload', methods=['POST'])
def upload_image():
    """Terima upload gambar dari client"""
    client_id = request.form.get('client_id')
    file = request.files.get('image')

    if not client_id or not file:
        return jsonify({"error": "invalid data"}), 400

    # pastikan folder upload tersedia
    os.makedirs("static/uploads", exist_ok=True)
    filename = f"{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    save_path = os.path.join("static/uploads", filename)
    file.save(save_path)

    # simpan data di memori client
    clients.setdefault(client_id, {})["last_image"] = filename

    # kirim notifikasi gambar baru ke admin
    socketio.emit("stream_frame", {
        "client_id": client_id,
        "image": f"/static/uploads/{filename}"
    })

    return jsonify({"status": "ok", "path": f"/static/uploads/{filename}"})

# -----------------------------
# API tambahan untuk admin
# -----------------------------
@app.route('/clients')
def get_clients():
    return jsonify(clients)

@app.route('/routes')
def get_routes():
    return jsonify(routes)

# -----------------------------
# Socket.IO Events
# -----------------------------
@socketio.on('register')
def register(data):
    cid = data.get("client_id")
    role = data.get("role")
    print(f"{role} terhubung: {cid}")

    if role == "admin":
        emit("clients_snapshot", clients)
    emit("notification_sent", {"client_id": cid, "message": "Terhubung ✅"})

@socketio.on('stream_frame')
def stream_frame(data):
    """(Deprecated) hanya jika client lama masih kirim base64"""
    client_id = data.get("client_id")
    image = data.get("image")
    if client_id and image:
        clients.setdefault(client_id, {})["last_image"] = image
        socketio.emit("stream_frame", {"client_id": client_id, "image": image})

@socketio.on('admin_send_notification')
def send_notif(data):
    emit("notification_sent", data)

# -----------------------------
# Jalankan server
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Server berjalan di http://localhost:{port}")
    socketio.run(app, host="0.0.0.0", port=port)
