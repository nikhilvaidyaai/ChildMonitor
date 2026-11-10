import os
import datetime
import csv
import io
from flask import (
    Flask, request, jsonify, render_template_string, 
    send_from_directory, redirect, url_for, session, Response
)
from werkzeug.utils import secure_filename
import database

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "shreeom-childmonitor-security-key-2026")

PARENT_PASSWORD = os.environ.get("PARENT_PASSWORD", "shreeom")

database.init_db()

BASE_DATA_DIR = os.path.join(os.path.dirname(__file__), "Children_Data")
os.makedirs(BASE_DATA_DIR, exist_ok=True)

def get_safe_child_folder(child_id):
    safe_id = "".join([c for c in str(child_id) if c.isalnum() or c in ("-", "_")])
    if not safe_id:
        safe_id = "device_default"
    folder_path = os.path.join(BASE_DATA_DIR, safe_id)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

def save_text_backup(child_id, data_type, content):
    try:
        child_folder = get_safe_child_folder(child_id)
        file_path = os.path.join(child_folder, f"{data_type}.txt")
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(content + "\n")
    except Exception as e:
        print(f"[BACKUP ERROR] {e}")

def is_authenticated():
    return session.get("authenticated") is True

# ================= LOGIN & LOGOUT ROUTES =================

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChildMonitor - Parent Login</title>
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --bg: #0f172a;
            --card: #1e293b;
        }
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: radial-gradient(circle at top, #1e293b, #0f172a);
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }
        .login-card {
            background: var(--card);
            border: 1px solid #334155;
            border-radius: 16px;
            padding: 36px 30px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            text-align: center;
        }
        .logo-icon { font-size: 46px; margin-bottom: 8px; }
        h2 { margin: 0 0 6px 0; font-size: 22px; font-weight: 700; color: #ffffff; }
        p.subtitle { color: #94a3b8; font-size: 13px; margin: 0 0 24px 0; }
        .form-group { text-align: left; margin-bottom: 20px; }
        label { display: block; font-size: 13px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; }
        input[type="password"] {
            width: 100%;
            padding: 12px 14px;
            background: #0f172a;
            border: 1px solid #475569;
            border-radius: 10px;
            color: white;
            font-size: 16px;
            outline: none;
            transition: 0.2s;
        }
        input[type="password"]:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.3);
        }
        .btn-submit {
            width: 100%;
            background: var(--primary);
            color: white;
            border: none;
            padding: 12px;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.2s;
        }
        .btn-submit:hover { background: var(--primary-dark); }
        .error-msg {
            background: rgba(220, 38, 38, 0.2);
            color: #f87171;
            border: 1px solid #dc2626;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 18px;
            font-size: 13px;
        }
        .footer-text { margin-top: 24px; font-size: 12px; color: #64748b; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo-icon">🛡️</div>
        <h2>Parent Dashboard</h2>
        <p class="subtitle">Child Safety & Parental Control</p>

        {% if error %}
        <div class="error-msg">⚠️ {{ error }}</div>
        {% endif %}

        <form method="POST" action="/login">
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" placeholder="Enter password (shreeom)" required autofocus>
            </div>
            <button type="submit" class="btn-submit">Sign In</button>
        </form>

        <div class="footer-text">Child Safety Monitoring System</div>
    </div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_authenticated():
        return redirect(url_for('dashboard'))

    error = None
    if request.method == 'POST':
        entered_pw = request.form.get('password', '').strip()
        if entered_pw == PARENT_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid password. Please enter correct password."

    return render_template_string(LOGIN_HTML, error=error)

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

# ================= CHILD APP API ENDPOINTS =================

@app.route('/get_commands/<child_id>', methods=['POST'])
def get_commands(child_id):
    data = request.json or {}
    child_name = data.get('child_name', 'Unknown_Device')
    battery = data.get('battery_level', None)
    is_charging = data.get('is_charging', None)
    wifi_ssid = data.get('wifi_ssid', None)

    database.register_or_update_device(
        device_id=child_id, 
        name=child_name, 
        battery=battery, 
        is_charging=is_charging, 
        wifi=wifi_ssid
    )

    if battery is not None and battery <= 15 and not is_charging:
        database.add_alert(
            device_id=child_id,
            alert_type="LOW_BATTERY",
            message=f"Low Battery Warning: {child_name} is at {battery}%."
        )

    controls = database.get_device_controls(child_id)
    if not controls:
        controls = {
            "device_id": child_id,
            "location_access": True,
            "message_access": False,
            "camera_access": "OFF",
            "audio_access": False,
            "audio_record_state": "IDLE",
            "gallery_access": False,
            "ring_alarm": False,
            "torch_access": False,
            "poll_interval": 5
        }

    return jsonify(controls), 200

@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.json or {}
    child_id = data.get('child_id')
    lat = data.get('latitude')
    lon = data.get('longitude')
    acc = data.get('accuracy', 0.0)
    time_str = data.get('time', database.now_str())

    if not child_id or lat is None or lon is None:
        return jsonify({"error": "Invalid data"}), 400

    try:
        lat = float(lat)
        lon = float(lon)
        acc = float(acc)
    except (ValueError, TypeError):
        return jsonify({"error": "Coordinates must be numbers"}), 400

    database.add_location(child_id, lat, lon, acc, time_str)
    database.register_or_update_device(child_id)

    log_entry = f"[{time_str}] -> Lat: {lat}, Lon: {lon}, Acc: {acc}m"
    save_text_backup(child_id, "location", log_entry)

    return jsonify({"status": "success"}), 200

@app.route('/log_sms', methods=['POST'])
def log_sms():
    data = request.json or {}
    child_id = data.get('child_id')
    sender = data.get('sender', 'Unknown')
    message = data.get('message', '')
    time_str = data.get('time', database.now_str())

    if not child_id:
        return jsonify({"error": "child_id required"}), 400

    database.add_sms_log(child_id, sender, message, time_str)
    save_text_backup(child_id, "sms", f"[{time_str}] -> From: {sender} | Msg: {message}")

    return jsonify({"status": "success"}), 200

@app.route('/upload_camera_photo', methods=['POST'])
def upload_camera_photo():
    if 'image' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['image']
    child_id = request.form.get('child_id')
    
    if not child_id:
        return jsonify({"error": "child_id required"}), 400

    filename = secure_filename(file.filename or f"capture_{int(datetime.datetime.now().timestamp())}.jpg")
    target_dir = os.path.join(get_safe_child_folder(child_id), "Camera_Captures")
    os.makedirs(target_dir, exist_ok=True)
    full_path = os.path.join(target_dir, filename)
    file.save(full_path)

    database.add_media_record(child_id, "image", full_path, filename)
    database.update_device_control(child_id, "camera_access", "OFF")

    print(f"[PHOTO RECEIVED] Device: {child_id}, File: {filename}")
    return jsonify({"status": "success", "filename": filename}), 200

@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file"}), 400
    
    file = request.files['audio']
    child_id = request.form.get('child_id')

    if not child_id:
        return jsonify({"error": "child_id required"}), 400

    filename = secure_filename(file.filename or f"audio_{int(datetime.datetime.now().timestamp())}.m4a")
    target_dir = os.path.join(get_safe_child_folder(child_id), "Audio_Records")
    os.makedirs(target_dir, exist_ok=True)
    full_path = os.path.join(target_dir, filename)
    file.save(full_path)

    database.add_media_record(child_id, "audio", full_path, filename)
    database.update_device_control(child_id, "audio_record_state", "IDLE")

    print(f"[AUDIO RECEIVED] Device: {child_id}, File: {filename}")
    return jsonify({"status": "success", "filename": filename}), 200

@app.route('/trigger_sos', methods=['POST'])
def trigger_sos():
    data = request.json or {}
    child_id = data.get('child_id')
    lat = data.get('latitude')
    lon = data.get('longitude')
    
    if not child_id:
        return jsonify({"error": "child_id required"}), 400

    database.add_alert(
        device_id=child_id,
        alert_type="SOS",
        message="EMERGENCY SOS: Child triggered panic button!",
        lat=lat,
        lon=lon
    )

    database.update_device_control(child_id, "location_access", 1)
    database.update_device_control(child_id, "camera_access", "FRONT")

    print(f"[SOS TRIGGERED] Device: {child_id} at {lat}, {lon}")
    return jsonify({"status": "SOS received"}), 200

# ================= MEDIA SERVING =================

@app.route('/media/<child_id>/<folder_type>/<filename>')
def serve_media(child_id, folder_type, filename):
    if not is_authenticated():
        return redirect(url_for('login'))

    allowed_folders = {"Camera_Captures", "Audio_Records"}
    if folder_type not in allowed_folders:
        return "Access denied", 403
    
    sec_filename = secure_filename(filename)
    safe_folder = get_safe_child_folder(child_id)
    folder_path = os.path.join(safe_folder, folder_type)

    if os.path.exists(os.path.join(folder_path, sec_filename)):
        return send_from_directory(folder_path, sec_filename)

    # Legacy folder fallbacks
    for prefix in ["My_Test_Phone_", "Device_", "Unknown_"]:
        alt_path = os.path.join(BASE_DATA_DIR, f"{prefix}{child_id}", folder_type)
        if os.path.exists(os.path.join(alt_path, sec_filename)):
            return send_from_directory(alt_path, sec_filename)

    return "File not found", 404

# ================= LIVE STATUS API =================

@app.route('/api/live_status')
def api_live_status():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401

    devices = database.get_all_devices()
    now_dt = datetime.datetime.now()

    result = []
    for d in devices:
        cid = d["id"]
        last_seen = d["last_seen"]
        diff_sec = 9999
        if isinstance(last_seen, str):
            try:
                last_seen_dt = datetime.datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
                diff_sec = (now_dt - last_seen_dt).total_seconds()
            except Exception:
                try:
                    last_seen_dt = datetime.datetime.fromisoformat(last_seen)
                    diff_sec = (now_dt - last_seen_dt).total_seconds()
                except Exception:
                    diff_sec = 9999

        status_str = "ONLINE" if diff_sec < 60 else ("IDLE" if diff_sec < 300 else "OFFLINE")
        latest_loc = database.get_latest_location(cid)

        result.append({
            "id": cid,
            "name": d["name"],
            "battery_level": d["battery_level"],
            "is_charging": bool(d["is_charging"]),
            "wifi_ssid": d["wifi_ssid"],
            "last_seen": str(d["last_seen"]),
            "status": status_str,
            "latest_loc": latest_loc,
            "camera_access": d.get("camera_access", "OFF"),
            "audio_record_state": d.get("audio_record_state", "IDLE"),
            "ring_alarm": bool(d.get("ring_alarm", 0)),
            "torch_access": bool(d.get("torch_access", 0))
        })

    active_alerts = database.get_active_alerts()
    return jsonify({
        "devices": result,
        "active_alerts": active_alerts,
        "server_time": database.now_str()
    })

# ================= WEB DASHBOARD =================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChildMonitor - Dashboard</title>
    <!-- Leaflet CSS & JS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --danger: #ef4444;
            --success: #10b981;
            --warning: #f59e0b;
            --dark: #0f172a;
            --card-bg: #ffffff;
            --bg: #f8fafc;
        }
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; background-color: var(--bg); color: #1e293b; }
        
        /* Modern Header */
        header { background: #0f172a; color: white; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .logo-box { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 18px; }
        .header-actions { display: flex; align-items: center; gap: 10px; }
        .status-pill { background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
        .btn-logout { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; text-decoration: none; transition: 0.2s; }
        .btn-logout:hover { background: #334155; color: white; }

        .container { padding: 20px; max-width: 1450px; margin: 0 auto; }

        /* Notification Toast */
        #toast-box { display: none; background: #1e293b; color: white; padding: 12px 20px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; font-weight: 500; border-left: 4px solid var(--primary); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }

        /* Alerts */
        .alert-banner { background: #fee2e2; border-left: 4px solid var(--danger); padding: 12px 16px; border-radius: 8px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
        .alert-banner b { color: var(--danger); font-size: 14px; }

        /* Layout Grid */
        .grid-main { display: grid; grid-template-columns: 360px 1fr; gap: 20px; }
        @media (max-width: 900px) { .grid-main { grid-template-columns: 1fr; } }

        /* Device Card */
        .device-card { background: white; border-radius: 12px; padding: 16px; border: 1px solid #e2e8f0; box-shadow: 0 2px 6px rgba(0,0,0,0.03); margin-bottom: 16px; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .device-title { font-size: 16px; font-weight: 700; color: #0f172a; margin: 0; }
        .device-id { font-size: 11px; color: #64748b; }
        
        .badge { padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
        .badge-online { background: #dcfce7; color: #15803d; }
        .badge-idle { background: #fef9c3; color: #a16207; }
        .badge-offline { background: #fee2e2; color: #b91c1c; }

        .meta-row { display: flex; align-items: center; gap: 10px; font-size: 12px; color: #64748b; margin-bottom: 12px; }
        .battery-box { display: flex; align-items: center; gap: 6px; }
        .battery-bar { width: 50px; height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }
        .battery-fill { height: 100%; transition: width 0.3s; }

        /* Action Buttons Grid */
        .controls-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 10px; font-size: 12px; font-weight: 600; border-radius: 6px; border: none; cursor: pointer; text-decoration: none; transition: 0.15s ease; }
        .btn-primary { background: var(--primary); color: white; }
        .btn-primary:hover { background: var(--primary-dark); }
        .btn-danger { background: var(--danger); color: white; }
        .btn-warning { background: var(--warning); color: white; }
        .btn-outline { background: #f8fafc; color: #334155; border: 1px solid #cbd5e1; }
        .btn-outline:hover { background: #f1f5f9; }
        .btn-recording { background: #dc2626; color: white; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 0.9; } 50% { opacity: 1; } 100% { opacity: 0.9; } }
        .col-full { grid-column: span 2; }

        /* Map */
        .map-wrapper { height: 400px; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 2px 6px rgba(0,0,0,0.04); margin-bottom: 18px; }
        #map { height: 100%; width: 100%; }

        /* Tabs */
        .tabs-nav { display: flex; gap: 6px; border-bottom: 2px solid #e2e8f0; margin-bottom: 16px; overflow-x: auto; }
        .tab-btn { padding: 9px 14px; background: none; border: none; font-size: 13px; font-weight: 600; color: #64748b; cursor: pointer; border-bottom: 3px solid transparent; white-space: nowrap; }
        .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }

        .tab-pane { display: none; }
        .tab-pane.active { display: block; }

        /* Photos Grid */
        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 14px; }
        .photo-card { background: white; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 1px 4px rgba(0,0,0,0.03); }
        .photo-card img { width: 100%; height: 130px; object-fit: cover; cursor: pointer; transition: 0.2s; }
        .photo-card img:hover { transform: scale(1.02); }
        .photo-card .meta { padding: 8px 10px; font-size: 11px; color: #64748b; }

        /* Audio Items */
        .audio-row { background: white; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #e2e8f0; flex-wrap: wrap; gap: 8px; }

        /* Tables */
        .data-table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; font-size: 13px; border: 1px solid #e2e8f0; }
        .data-table th { background: #f8fafc; padding: 9px 12px; text-align: left; font-weight: 600; color: #475569; }
        .data-table td { padding: 9px 12px; border-top: 1px solid #f1f5f9; }

        /* Lightbox */
        #imgModal { display: none; position: fixed; z-index: 9999; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); align-items: center; justify-content: center; }
        #imgModal img { max-width: 90%; max-height: 85%; border-radius: 8px; }
    </style>
</head>
<body>
    <header>
        <div class="logo-box">🛡️ ChildMonitor</div>
        <div class="header-actions">
            <span class="status-pill">● Live Tracking</span>
            <a href="/logout" class="btn-logout">Logout</a>
        </div>
    </header>

    <div class="container">
        <!-- Toast Feedback -->
        <div id="toast-box"></div>

        <!-- Active Alerts -->
        {% for alert in active_alerts %}
        <div class="alert-banner">
            <div>
                <b>{{ alert.alert_type }}:</b> {{ alert.message }}
                <span style="font-size: 11px; color: #64748b; margin-left: 8px;">({{ alert.timestamp }})</span>
            </div>
            <a href="/resolve_alert/{{ alert.id }}" class="btn btn-outline" style="background: white; font-size: 11px;">Dismiss</a>
        </div>
        {% endfor %}

        <div class="grid-main">
            <!-- Left: Devices List & Quick Controls -->
            <div class="sidebar-column">
                <h3 style="margin: 0 0 12px 0; font-size: 15px; color: #334155;">Connected Devices</h3>

                {% if not devices %}
                <div class="device-card" style="text-align: center; color: #64748b; padding: 25px;">
                    No device connected yet.<br>
                    <small>Open the app on mobile to connect automatically.</small>
                </div>
                {% endif %}

                {% for d in devices %}
                <div class="device-card" id="card-{{ d.id }}">
                    <div class="card-header">
                        <div>
                            <div class="device-title">{{ d.name }}</div>
                            <div class="device-id">ID: {{ d.id }}</div>
                        </div>
                        <span class="badge {{ 'badge-online' if status[d.id] == 'ONLINE' else ('badge-idle' if status[d.id] == 'IDLE' else 'badge-offline') }}" id="badge-{{ d.id }}">{{ status[d.id] }}</span>
                    </div>

                    <div class="meta-row">
                        <div class="battery-box">
                            <span>🔋 {{ d.battery_level }}%</span>
                            <div class="battery-bar">
                                <div class="battery-fill" style="width: {{ d.battery_level }}%; background-color: {{ '#10b981' if d.battery_level > 25 else '#ef4444' }};"></div>
                            </div>
                        </div>
                        <span>📶 {{ d.wifi_ssid }}</span>
                    </div>

                    <!-- Clean Remote Action Buttons -->
                    <div class="controls-grid">
                        <button onclick="triggerCamera('{{ d.id }}', 'FRONT')" class="btn btn-primary">
                            🤳 Front Cam
                        </button>
                        <button onclick="triggerCamera('{{ d.id }}', 'BACK')" class="btn btn-primary">
                            📷 Back Cam
                        </button>

                        {% if d.audio_record_state == 'START' %}
                        <a href="/audio_command/{{ d.id }}/stop" class="btn btn-recording col-full" onclick="showToast('Stopping audio recording and uploading...')">
                            ⏹️ Stop & Send Audio
                        </a>
                        {% else %}
                        <a href="/audio_command/{{ d.id }}/start" class="btn btn-danger col-full" onclick="showToast('Audio recording started on child\\'s phone...')">
                            🎙️ Record Audio Clip
                        </a>
                        {% endif %}

                        <a href="/trigger_alarm/{{ d.id }}" class="btn {{ 'btn-danger' if d.ring_alarm else 'btn-warning' }}" onclick="return confirm('Ring child\'s phone loudly?');">
                            🔔 {{ 'Stop Ring' if d.ring_alarm else 'Ring Phone' }}
                        </a>
                        <a href="/toggle/{{ d.id }}/torch_access" class="btn {{ 'btn-primary' if d.torch_access else 'btn-outline' }}">
                            💡 {{ 'Torch OFF' if d.torch_access else 'Torch ON' }}
                        </a>

                        {% set loc = details[d.id].latest_loc %}
                        {% if loc %}
                        <a href="https://www.google.com/maps/search/?api=1&query={{ loc.latitude }},{{ loc.longitude }}" target="_blank" class="btn btn-outline col-full" style="color: var(--primary);">
                            📍 Open in Google Maps
                        </a>
                        {% endif %}
                        <a href="/delete_device/{{ d.id }}" class="btn btn-outline col-full" style="color: var(--danger); font-size: 11px;" onclick="return confirm('Remove this device and its history?');">
                            🗑️ Delete Device
                        </a>
                    </div>
                </div>
                {% endfor %}
            </div>

            <!-- Right: Live Map & Tabs -->
            <div class="content-column">
                <div class="map-wrapper">
                    <div id="map"></div>
                </div>

                <!-- Tabs Navigation -->
                <div class="tabs-nav">
                    <button class="tab-btn active" onclick="openTab(event, 'tab-photos')">📸 Photos ({{ details[devices[0].id].photos|length if devices else 0 }})</button>
                    <button class="tab-btn" onclick="openTab(event, 'tab-audios')">🎙️ Audio Recordings ({{ details[devices[0].id].audios|length if devices else 0 }})</button>
                    <button class="tab-btn" onclick="openTab(event, 'tab-geofence')">🌐 Geofences</button>
                    <button class="tab-btn" onclick="openTab(event, 'tab-history')">📍 Travel History</button>
                    <button class="tab-btn" onclick="openTab(event, 'tab-sms')">💬 SMS</button>
                </div>

                <!-- Tab 1: Photos -->
                <div id="tab-photos" class="tab-pane active">
                    <div class="gallery-grid" id="photos-container">
                        {% set ns = namespace(found=false) %}
                        {% for d in devices %}
                            {% for photo in details[d.id].photos %}
                                {% set ns.found = true %}
                                <div class="photo-card">
                                    <img src="/media/{{ d.id }}/Camera_Captures/{{ photo.filename }}" alt="Camera Snap" loading="lazy" onclick="showModal(this.src)">
                                    <div class="meta">
                                        <b>{{ d.name }}</b><br>
                                        {{ photo.timestamp }}
                                    </div>
                                </div>
                            {% endfor %}
                        {% endfor %}
                        {% if not ns.found %}
                            <div style="grid-column: 1/-1; padding: 25px; text-align: center; color: #64748b; background: white; border-radius: 8px; border: 1px solid #e2e8f0;">
                                No photos captured yet.<br>Click <b>Front Cam</b> or <b>Back Cam</b> on the left to capture.
                            </div>
                        {% endif %}
                    </div>
                </div>

                <!-- Tab 2: Audio -->
                <div id="tab-audios" class="tab-pane">
                    {% set ns2 = namespace(found=false) %}
                    {% for d in devices %}
                        {% for aud in details[d.id].audios %}
                            {% set ns2.found = true %}
                            <div class="audio-row">
                                <div>
                                    <b>{{ d.name }}</b> - <code>{{ aud.filename }}</code><br>
                                    <small style="color: #64748b;">{{ aud.timestamp }}</small>
                                </div>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <audio controls src="/media/{{ d.id }}/Audio_Records/{{ aud.filename }}"></audio>
                                    <a href="/media/{{ d.id }}/Audio_Records/{{ aud.filename }}" download class="btn btn-outline" style="font-size: 11px;">⬇️ Download</a>
                                </div>
                            </div>
                        {% endfor %}
                    {% endfor %}
                    {% if not ns2.found %}
                        <div style="padding: 25px; text-align: center; color: #64748b; background: white; border-radius: 8px; border: 1px solid #e2e8f0;">
                            No audio recordings yet.<br>Click <b>Record Audio Clip</b> on the left, then click <b>Stop & Send</b> when done.
                        </div>
                    {% endif %}
                </div>

                <!-- Tab 3: Geofences -->
                <div id="tab-geofence" class="tab-pane">
                    {% for d in devices %}
                    <div style="margin-bottom: 20px;">
                        <h4 style="margin: 0 0 10px 0;">Safe Zones for {{ d.name }}</h4>
                        <form action="/add_geofence" method="POST" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;">
                            <input type="hidden" name="device_id" value="{{ d.id }}">
                            <input type="text" name="name" placeholder="Zone Name (e.g. Home, School)" required style="padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; flex: 1;">
                            <input type="number" step="any" id="geo-lat-{{ d.id }}" name="latitude" placeholder="Latitude" required style="width: 120px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px;">
                            <input type="number" step="any" id="geo-lon-{{ d.id }}" name="longitude" placeholder="Longitude" required style="width: 120px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px;">
                            <input type="number" name="radius_meters" placeholder="Radius (m)" value="200" required style="width: 90px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px;">
                            <button type="submit" class="btn btn-primary">+ Add Zone</button>
                        </form>

                        <table class="data-table">
                            <tr>
                                <th>Name</th>
                                <th>Coordinates</th>
                                <th>Radius</th>
                                <th>Action</th>
                            </tr>
                            {% for f in details[d.id].geofences %}
                            <tr>
                                <td><b>{{ f.name }}</b></td>
                                <td>{{ f.latitude }}, {{ f.longitude }}</td>
                                <td>{{ f.radius_meters }}m</td>
                                <td><a href="/delete_geofence/{{ f.id }}" style="color: var(--danger); font-weight: 600; text-decoration: none;">Delete</a></td>
                            </tr>
                            {% endfor %}
                        </table>
                    </div>
                    {% endfor %}
                </div>

                <!-- Tab 4: Travel History -->
                <div id="tab-history" class="tab-pane">
                    {% for d in devices %}
                    <div style="margin-bottom: 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <h4 style="margin: 0;">{{ d.name }} Location History</h4>
                            <a href="/export_locations/{{ d.id }}" class="btn btn-outline" style="font-size: 11px;">📊 Export CSV</a>
                        </div>
                        <table class="data-table">
                            <tr>
                                <th>Time</th>
                                <th>Latitude</th>
                                <th>Longitude</th>
                                <th>Accuracy</th>
                            </tr>
                            {% for loc in details[d.id].loc_history[-15:]|reverse %}
                            <tr>
                                <td>{{ loc.timestamp }}</td>
                                <td>{{ loc.latitude }}</td>
                                <td>{{ loc.longitude }}</td>
                                <td>{{ loc.accuracy }}m</td>
                            </tr>
                            {% endfor %}
                        </table>
                    </div>
                    {% endfor %}
                </div>

                <!-- Tab 5: SMS -->
                <div id="tab-sms" class="tab-pane">
                    {% for d in devices %}
                        {% for s in details[d.id].sms %}
                        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: bold; margin-bottom: 4px;">
                                <span>From: {{ s.sender }}</span>
                                <span style="color: #64748b; font-weight: normal;">{{ s.timestamp }}</span>
                            </div>
                            <div style="font-size: 13px; color: #334155;">{{ s.message }}</div>
                        </div>
                        {% endfor %}
                    {% endfor %}
                </div>

            </div>
        </div>
    </div>

    <!-- Modal Lightbox -->
    <div id="imgModal" onclick="this.style.display='none'">
        <img id="modalImg" src="">
    </div>

    <script>
        var map = L.map('map').setView([19.0760, 72.8777], 14);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap'
        }).addTo(map);

        var markers = {};
        var pathLayers = {};
        var bounds = [];
        var colors = ['#2563eb', '#10b981', '#ef4444', '#8b5cf6'];

        {% for d in devices %}
            {% set loc = details[d.id].latest_loc %}
            {% if loc %}
                markers['{{ d.id }}'] = L.marker([{{ loc.latitude }}, {{ loc.longitude }}]).addTo(map)
                    .bindPopup("<b>{{ d.name }}</b><br>🔋 {{ d.battery_level }}%<br>{{ loc.timestamp }}");
                bounds.push([{{ loc.latitude }}, {{ loc.longitude }}]);
            {% endif %}

            var points_{{ loop.index }} = [
                {% for p in details[d.id].loc_history %}
                    [{{ p.latitude }}, {{ p.longitude }}],
                {% endfor %}
            ];
            if (points_{{ loop.index }}.length > 1) {
                var c = colors[{{ loop.index0 }} % colors.length];
                pathLayers['{{ d.id }}'] = L.polyline(points_{{ loop.index }}, {color: c, weight: 4, opacity: 0.8}).addTo(map);
            }

            {% for f in details[d.id].geofences %}
                L.circle([{{ f.latitude }}, {{ f.longitude }}], {
                    color: '#10b981',
                    fillColor: '#86efac',
                    fillOpacity: 0.25,
                    radius: {{ f.radius_meters }}
                }).addTo(map).bindPopup("<b>Safe Zone: {{ f.name }}</b>");
            {% endfor %}
        {% endfor %}

        if (bounds.length > 0) {
            map.fitBounds(bounds, {padding: [30, 30], maxZoom: 16});
        }

        // Map Click sets Geofence coordinates
        map.on('click', function(e) {
            var lat = e.latlng.lat.toFixed(6);
            var lon = e.latlng.lng.toFixed(6);
            {% if devices %}
                var firstDevId = '{{ devices[0].id }}';
                var latInput = document.getElementById('geo-lat-' + firstDevId);
                var lonInput = document.getElementById('geo-lon-' + firstDevId);
                if (latInput && lonInput) {
                    latInput.value = lat;
                    lonInput.value = lon;
                    showToast("Coordinates set from map: " + lat + ", " + lon);
                }
            {% endif %}
        });

        function showToast(msg) {
            var tb = document.getElementById('toast-box');
            tb.innerText = msg;
            tb.style.display = 'block';
            setTimeout(function() { tb.style.display = 'none'; }, 6000);
        }

        function triggerCamera(devId, mode) {
            showToast("Requesting " + mode + " camera photo... Please wait 3-5 seconds.");
            fetch('/set_camera/' + devId + '/' + mode)
                .then(() => {
                    setTimeout(() => { window.location.reload(); }, 6000);
                });
        }

        function openTab(evt, tabId) {
            var panes = document.getElementsByClassName("tab-pane");
            for (var i = 0; i < panes.length; i++) panes[i].classList.remove("active");
            var btns = document.getElementsByClassName("tab-btn");
            for (var i = 0; i < btns.length; i++) btns[i].classList.remove("active");
            document.getElementById(tabId).classList.add("active");
            if (evt) evt.currentTarget.classList.add("active");
            localStorage.setItem("activeTab", tabId);
        }

        var savedTab = localStorage.getItem("activeTab");
        if (savedTab && document.getElementById(savedTab)) {
            var btn = document.querySelector("button[onclick*='" + savedTab + "']");
            if (btn) btn.click();
        }

        function showModal(src) {
            document.getElementById('modalImg').src = src;
            document.getElementById('imgModal').style.display = 'flex';
        }

        // Live Poll (Every 4 seconds)
        setInterval(function() {
            fetch('/api/live_status')
                .then(r => r.json())
                .then(data => {
                    if (!data || !data.devices) return;
                    data.devices.forEach(d => {
                        var badge = document.getElementById('badge-' + d.id);
                        if (badge) {
                            badge.innerText = d.status;
                            badge.className = 'badge ' + (d.status === 'ONLINE' ? 'badge-online' : (d.status === 'IDLE' ? 'badge-idle' : 'badge-offline'));
                        }
                        if (d.latest_loc) {
                            var pos = [d.latest_loc.latitude, d.latest_loc.longitude];
                            if (markers[d.id]) {
                                markers[d.id].setLatLng(pos);
                            } else {
                                markers[d.id] = L.marker(pos).addTo(map).bindPopup("<b>" + d.name + "</b>");
                            }
                        }
                    });
                })
                .catch(err => console.log(err));
        }, 4000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    if not is_authenticated():
        return redirect(url_for('login'))

    devices = database.get_all_devices()
    now_dt = datetime.datetime.now()

    devices_status = {}
    for d in devices:
        last_seen = d["last_seen"]
        diff_sec = 9999
        if isinstance(last_seen, str):
            try:
                last_seen_dt = datetime.datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
                diff_sec = (now_dt - last_seen_dt).total_seconds()
            except Exception:
                try:
                    last_seen_dt = datetime.datetime.fromisoformat(last_seen)
                    diff_sec = (now_dt - last_seen_dt).total_seconds()
                except Exception:
                    diff_sec = 9999

        devices_status[d["id"]] = "ONLINE" if diff_sec < 60 else ("IDLE" if diff_sec < 300 else "OFFLINE")

    active_alerts = database.get_active_alerts()

    device_details = {}
    for d in devices:
        cid = d["id"]
        device_details[cid] = {
            "latest_loc": database.get_latest_location(cid),
            "loc_history": database.get_location_history(cid, limit=50),
            "photos": database.get_media_records(cid, media_type="image", limit=20),
            "audios": database.get_media_records(cid, media_type="audio", limit=15),
            "sms": database.get_sms_logs(cid, limit=15),
            "geofences": database.get_geofences(cid)
        }

    return render_template_string(
        DASHBOARD_HTML, 
        devices=devices, 
        status=devices_status, 
        details=device_details, 
        active_alerts=active_alerts
    )

# ================= ACTIONS & TOGGLES =================

@app.route('/toggle/<child_id>/<feature>')
def toggle_feature(child_id, feature):
    if not is_authenticated():
        return redirect(url_for('login'))
    controls = database.get_device_controls(child_id)
    if controls and feature in controls:
        curr = controls[feature]
        new_val = 0 if curr else 1
        database.update_device_control(child_id, feature, new_val)
    return redirect(url_for('dashboard'))

@app.route('/audio_command/<child_id>/<action>')
def audio_command(child_id, action):
    if not is_authenticated():
        return redirect(url_for('login'))
    if action == "start":
        database.update_device_control(child_id, "audio_record_state", "START")
    elif action == "stop":
        database.update_device_control(child_id, "audio_record_state", "STOP")
    return redirect(url_for('dashboard'))

@app.route('/trigger_alarm/<child_id>')
def trigger_alarm(child_id):
    if not is_authenticated():
        return redirect(url_for('login'))
    controls = database.get_device_controls(child_id)
    if controls:
        curr = controls.get("ring_alarm", False)
        new_val = 0 if curr else 1
        database.update_device_control(child_id, "ring_alarm", new_val)
    return redirect(url_for('dashboard'))

@app.route('/set_camera/<child_id>/<mode>')
def set_camera(child_id, mode):
    if not is_authenticated():
        return redirect(url_for('login'))
    if mode in ["FRONT", "BACK", "OFF"]:
        database.update_device_control(child_id, "camera_access", mode)
    return redirect(url_for('dashboard'))

@app.route('/resolve_alert/<int:alert_id>')
def resolve_alert(alert_id):
    if not is_authenticated():
        return redirect(url_for('login'))
    database.resolve_alert(alert_id)
    return redirect(url_for('dashboard'))

@app.route('/delete_device/<child_id>')
def delete_device(child_id):
    if not is_authenticated():
        return redirect(url_for('login'))
    database.delete_device(child_id)
    return redirect(url_for('dashboard'))

@app.route('/add_geofence', methods=['POST'])
def add_geofence():
    if not is_authenticated():
        return redirect(url_for('login'))
    device_id = request.form.get('device_id')
    name = request.form.get('name', 'Safe Zone').strip()
    try:
        lat = float(request.form.get('latitude', 0.0))
        lon = float(request.form.get('longitude', 0.0))
        radius = float(request.form.get('radius_meters', 200))
        if device_id and name and lat and lon:
            database.add_geofence(device_id, name, lat, lon, radius)
    except (ValueError, TypeError) as e:
        print("[GEOFENCE ERROR]", e)
    return redirect(url_for('dashboard'))

@app.route('/delete_geofence/<int:fence_id>')
def delete_geofence(fence_id):
    if not is_authenticated():
        return redirect(url_for('login'))
    database.delete_geofence(fence_id)
    return redirect(url_for('dashboard'))

@app.route('/export_locations/<child_id>')
def export_locations(child_id):
    if not is_authenticated():
        return redirect(url_for('login'))
    
    locations = database.get_location_history(child_id, limit=500)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Device ID", "Latitude", "Longitude", "Accuracy (m)", "Timestamp"])
    for loc in locations:
        writer.writerow([loc.get("id"), child_id, loc.get("latitude"), loc.get("longitude"), loc.get("accuracy"), loc.get("timestamp")])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=locations_{child_id}.csv"}
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"ChildMonitor server starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
