from flask import Flask, request, render_template
from flask_socketio import SocketIO
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

user_locations = {}

def get_client_ip():
    """
    Ambil IP client dengan prioritas:
    1) X-Forwarded-For (ambil elemen pertama jika ada list)
    2) request.remote_addr
    """
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        # X-Forwarded-For bisa berisi "client, proxy1, proxy2"
        ip = forwarded.split(',')[0].strip()
        if ip:
            return ip
    return request.remote_addr

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/monitor')
def monitor():
    return render_template('monitor.html')

@app.route('/report', methods=['POST'])
def report():
    data = request.get_json() or {}
    lat = data.get('latitude')
    lon = data.get('longitude')

    # Gunakan IP klien sebagai user id
    client_ip = get_client_ip() or "unknown"

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Simpan lokasi terakhir tiap IP
    user_locations[client_ip] = {'lat': lat, 'lon': lon, 'time': timestamp}

    # Simpan log (append)
    with open('log.txt', 'a', encoding='utf-8') as f:
        f.write(f"{timestamp} - {client_ip} => Lat: {lat}, Lon: {lon}\n")

    # Broadcast ke semua monitor clients
    socketio.emit('update_location', {
        'user': client_ip,
        'lat': lat,
        'lon': lon,
        'time': timestamp
    })

    print(f"[+] Lokasi {client_ip}: {lat}, {lon}")
    return {'status': 'ok'}

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
