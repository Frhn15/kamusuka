from flask import Flask, request, render_template
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/report', methods=['POST'])
def report():
    data = request.get_json()
    lat = data.get('latitude')
    lon = data.get('longitude')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with open('log.txt', 'a') as f:
        f.write(f"{timestamp} - Lat: {lat}, Lon: {lon}\n")

    print(f"[+] Lokasi diterima: {lat}, {lon}")
    return {'status': 'ok'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
