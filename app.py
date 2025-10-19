from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Simpan lokasi terakhir setiap user
user_locations = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/monitor')
def monitor():
    return render_template('monitor.html')

@app.route('/report', methods=['POST'])
def report():
    data = request.get_json()
    lat = data.get('latitude')
    lon = data.get('longitude')
    user = data.get('user', 'anonymous')

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_locations[user] = {'lat': lat, 'lon': lon, 'time': timestamp}

    # Simpan ke file log
    with open('log.txt', 'a') as f:
        f.write(f"{timestamp} - {user} => Lat: {lat}, Lon: {lon}\n")

    # Broadcast ke semua halaman monitor
    socketio.emit('update_location', {
        'user': user,
        'lat': lat,
        'lon': lon,
        'time': timestamp
    })

    print(f"[+] Lokasi {user}: {lat}, {lon}")
    return {'status': 'ok'}

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
