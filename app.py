# app.py
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from datetime import datetime
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

clients = {}   # client_id -> latest info
routes = {}    # client_id -> list of {lat, lon, time}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/report', methods=['POST'])
def report():
    data = request.get_json() or {}
    client_id = data.get('client_id')
    try:
        lat = float(data.get('latitude', 0))
        lon = float(data.get('longitude', 0))
    except (TypeError, ValueError):
        return jsonify({"error": "latitude/longitude invalid"}), 400

    if not client_id:
        return jsonify({"error": "client_id required"}), 400

    ts = datetime.utcnow().isoformat()

    clients[client_id] = {
        "latitude": lat,
        "longitude": lon,
        "last_seen": ts
    }

    routes.setdefault(client_id, []).append({"lat": lat, "lon": lon, "time": ts})

    # kirim ke semua yang terhubung (admin UI akan menerima ini)
    socketio.emit('location_update', {
        "client_id": client_id,
        "latitude": lat,
        "longitude": lon,
        "last_seen": ts
    })

    return jsonify({"status":"ok"})

@app.route('/clients')
def get_clients():
    return jsonify(clients)

@app.route('/routes')
def get_routes():
    return jsonify(routes)

@socketio.on('register')
def on_register(data):
    role = data.get('role')
    cid = data.get('client_id')
    print(f"terhubung role={role} id={cid}")
    if role == 'admin':
        # kirim snapshot awal clients ke admin yang baru connect
        emit('clients_snapshot', clients)

@socketio.on('stream_frame')
def on_stream_frame(data):
    # optional: kita simpan frame di memory, tapi tidak wajib
    client_id = data.get('client_id')
    image = data.get('image')
    if not client_id or not image:
        return
    # simpan last image (base64) — hati2 memori jika banyak client/stream
    clients.setdefault(client_id, {})['last_image'] = image
    # kirim ke admin UI
    socketio.emit('stream_frame', {"client_id": client_id, "image": image})

@socketio.on('admin_send_notification')
def on_admin_send_notification(data):
    # terima dari admin UI, forward ke semua client (atau sesuaikan)
    socketio.emit('notification_sent', data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
