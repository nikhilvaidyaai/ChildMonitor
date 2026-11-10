import sqlite3
import os
import math
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "child_monitor.db")

def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    
    # १. उपकरणांची प्राथमिक माहिती (Devices)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        battery_level INTEGER DEFAULT 100,
        is_charging INTEGER DEFAULT 0,
        wifi_ssid TEXT DEFAULT 'Unknown',
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # २. रिमोट कंट्रोल्स आणि आदेश (Device Controls)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS device_controls (
        device_id TEXT PRIMARY KEY,
        location_access INTEGER DEFAULT 1,
        message_access INTEGER DEFAULT 0,
        camera_access TEXT DEFAULT 'OFF',
        audio_access INTEGER DEFAULT 0,
        gallery_access INTEGER DEFAULT 0,
        ring_alarm INTEGER DEFAULT 0,
        torch_access INTEGER DEFAULT 0,
        poll_interval INTEGER DEFAULT 30,
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
    );
    """)

    # नवीन कॉलम अस्तित्वात नसल्यास जोडणे (Backwards Compatibility)
    for col_def in ["ring_alarm INTEGER DEFAULT 0", "torch_access INTEGER DEFAULT 0", "audio_record_state TEXT DEFAULT 'IDLE'"]:
        try:
            cursor.execute(f"ALTER TABLE device_controls ADD COLUMN {col_def}")
        except Exception:
            pass

    # ३. लोकेशन हिस्ट्री (Locations)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        latitude REAL,
        longitude REAL,
        accuracy REAL DEFAULT 0.0,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
    );
    """)

    # ४. एसएमएस लॉग्स (SMS Logs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sms_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        sender TEXT,
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
    );
    """)

    # ५. कॅमेरा व ऑडिओ मीडिया रेकॉर्ड्स (Media Records)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS media_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        media_type TEXT, -- 'image' or 'audio'
        file_path TEXT,
        filename TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
    );
    """)

    # ६. जिओफेन्स - सुरक्षित क्षेत्रे (Geofences)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS geofences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        radius_meters REAL NOT NULL DEFAULT 200,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
    );
    """)

    # ७. आणीबाणी व सुरक्षा सूचना (Alerts / SOS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        alert_type TEXT, -- 'SOS', 'LOW_BATTERY', 'GEOFENCE_EXIT'
        message TEXT,
        latitude REAL,
        longitude REAL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_resolved INTEGER DEFAULT 0,
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()

# ========== डिव्हाइस मॅनेजमेंट ==========

def register_or_update_device(device_id, name="Unknown_Device", battery=None, is_charging=None, wifi=None):
    conn = get_db()
    cursor = conn.cursor()
    curr_ts = now_str()

    cursor.execute("SELECT id, name FROM devices WHERE id = ?", (device_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("""
            INSERT INTO devices (id, name, battery_level, is_charging, wifi_ssid, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            device_id, 
            name, 
            battery if battery is not None else 100, 
            1 if is_charging else 0, 
            wifi if wifi else 'Unknown', 
            curr_ts,
            curr_ts
        ))
        cursor.execute("INSERT OR IGNORE INTO device_controls (device_id) VALUES (?)", (device_id,))
    else:
        updates = ["last_seen = ?"]
        params = [curr_ts]
        if name and name not in ["Unknown_Device", "Device"]:
            updates.append("name = ?")
            params.append(name)
        if battery is not None:
            updates.append("battery_level = ?")
            params.append(battery)
        if is_charging is not None:
            updates.append("is_charging = ?")
            params.append(1 if is_charging else 0)
        if wifi is not None:
            updates.append("wifi_ssid = ?")
            params.append(wifi)
        
        params.append(device_id)
        cursor.execute(f"UPDATE devices SET {', '.join(updates)} WHERE id = ?", params)
        cursor.execute("INSERT OR IGNORE INTO device_controls (device_id) VALUES (?)", (device_id,))

    conn.commit()
    conn.close()

def get_device_controls(device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM device_controls WHERE device_id = ?", (device_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        keys = row.keys()
        return {
            "device_id": row["device_id"],
            "location_access": bool(row["location_access"]),
            "message_access": bool(row["message_access"]),
            "camera_access": row["camera_access"],
            "audio_access": bool(row["audio_access"]),
            "audio_record_state": row["audio_record_state"] if "audio_record_state" in keys and row["audio_record_state"] else "IDLE",
            "gallery_access": bool(row["gallery_access"]),
            "ring_alarm": bool(row["ring_alarm"]) if "ring_alarm" in keys else False,
            "torch_access": bool(row["torch_access"]) if "torch_access" in keys else False,
            "poll_interval": row["poll_interval"] if "poll_interval" in keys else 30
        }
    return None

def update_device_control(device_id, field, value):
    valid_fields = [
        "location_access", "message_access", "camera_access", 
        "audio_access", "audio_record_state", "gallery_access", "ring_alarm", "torch_access", "poll_interval"
    ]
    if field not in valid_fields:
        return False
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO device_controls (device_id) VALUES (?)", (device_id,))
    cursor.execute(f"UPDATE device_controls SET {field} = ? WHERE device_id = ?", (value, device_id))
    conn.commit()
    conn.close()
    return True

def get_all_devices():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.id, d.name, d.battery_level, d.is_charging, d.wifi_ssid, d.last_seen, d.created_at
        FROM devices d
        ORDER BY d.last_seen DESC
    """)
    rows = cursor.fetchall()
    devices = []
    for r in rows:
        d = dict(r)
        ctrl = get_device_controls(d["id"])
        if ctrl:
            d["location_access"] = ctrl.get("location_access", True)
            d["message_access"] = ctrl.get("message_access", False)
            d["camera_access"] = ctrl.get("camera_access", "OFF")
            d["audio_access"] = ctrl.get("audio_access", False)
            d["audio_record_state"] = ctrl.get("audio_record_state", "IDLE")
            d["gallery_access"] = ctrl.get("gallery_access", False)
            d["ring_alarm"] = ctrl.get("ring_alarm", False)
            d["torch_access"] = ctrl.get("torch_access", False)
        else:
            d["location_access"] = True
            d["message_access"] = False
            d["camera_access"] = "OFF"
            d["audio_access"] = False
            d["audio_record_state"] = "IDLE"
            d["gallery_access"] = False
            d["ring_alarm"] = False
            d["torch_access"] = False
        devices.append(d)
    conn.close()
    return devices

def delete_device(device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    cursor.execute("DELETE FROM device_controls WHERE device_id = ?", (device_id,))
    cursor.execute("DELETE FROM locations WHERE device_id = ?", (device_id,))
    cursor.execute("DELETE FROM alerts WHERE device_id = ?", (device_id,))
    cursor.execute("DELETE FROM media_records WHERE device_id = ?", (device_id,))
    cursor.execute("DELETE FROM sms_logs WHERE device_id = ?", (device_id,))
    cursor.execute("DELETE FROM geofences WHERE device_id = ?", (device_id,))
    conn.commit()
    conn.close()

# ========== लोकेशन आणि जिओफेन्स ==========

def haversine_distance(lat1, lon1, lat2, lon2):
    """दोन कोऑर्डिनेट्समधील अंतर (मीटरमध्ये) अचूक मोजणे"""
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371000  # पृथ्वीची त्रिज्या मीटरमध्ये
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2.0)**2 + \
            math.cos(phi1) * math.cos(phi2) * \
            math.sin(delta_lambda / 2.0)**2
        a = min(1.0, max(0.0, a))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except Exception:
        return 0.0

def add_location(device_id, lat, lon, accuracy=0.0, timestamp=None):
    conn = get_db()
    cursor = conn.cursor()
    ts = timestamp if timestamp else now_str()
    cursor.execute("""
        INSERT INTO locations (device_id, latitude, longitude, accuracy, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (device_id, float(lat), float(lon), float(accuracy), ts))
    conn.commit()

    # जिओफेन्स मर्यादा तपासणे
    cursor.execute("SELECT * FROM geofences WHERE device_id = ? AND is_active = 1", (device_id,))
    fences = cursor.fetchall()
    
    if fences:
        # जर पालकांनी सुरक्षित क्षेत्रे ठरवली असतील:
        # मूल कोणत्याही एका सुरक्षित क्षेत्रात उपस्थित आहे का?
        inside_any = False
        distances = []
        for fence in fences:
            dist = haversine_distance(lat, lon, fence["latitude"], fence["longitude"])
            distances.append((fence["name"], int(dist), int(fence["radius_meters"])))
            if dist <= fence["radius_meters"]:
                inside_any = True
                break
        
        # जर मूल सर्वच्या सर्व सुरक्षित क्षेत्रांबाहेर गेले असेल, तरच अलर्ट देणे
        if not inside_any:
            fence_str = ", ".join([f"{name} ({d}m)" for name, d, _ in distances])
            msg = f"⚠️ मूल सर्व सुरक्षित क्षेत्रांच्या बाहेर पडले आहे! ({fence_str})"
            
            cursor.execute("""
                SELECT id FROM alerts 
                WHERE device_id = ? AND alert_type = 'GEOFENCE_EXIT' AND is_resolved = 0
            """, (device_id,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO alerts (device_id, alert_type, message, latitude, longitude, timestamp)
                    VALUES (?, 'GEOFENCE_EXIT', ?, ?, ?, ?)
                """, (device_id, msg, lat, lon, ts))
                conn.commit()

    conn.close()

def get_latest_location(device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM locations WHERE device_id = ? ORDER BY id DESC LIMIT 1
    """, (device_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_location_history(device_id, limit=100):
    conn = get_db()
    cursor = conn.cursor()
    # ताज्या नोंदी मिळवून मग त्या कालक्रमानुसार (ASC) देणे
    cursor.execute("""
        SELECT * FROM (
            SELECT * FROM locations 
            WHERE device_id = ? 
            ORDER BY id DESC 
            LIMIT ?
        ) ORDER BY id ASC
    """, (device_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ========== एसएमएस आणि मीडिया ==========

def add_sms_log(device_id, sender, message, timestamp=None):
    conn = get_db()
    cursor = conn.cursor()
    ts = timestamp if timestamp else now_str()
    cursor.execute("""
        INSERT INTO sms_logs (device_id, sender, message, timestamp)
        VALUES (?, ?, ?, ?)
    """, (device_id, sender, message, ts))
    conn.commit()
    conn.close()

def get_sms_logs(device_id, limit=50):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM sms_logs WHERE device_id = ? ORDER BY id DESC LIMIT ?
    """, (device_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_media_record(device_id, media_type, file_path, filename):
    conn = get_db()
    cursor = conn.cursor()
    ts = now_str()
    cursor.execute("""
        INSERT INTO media_records (device_id, media_type, file_path, filename, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (device_id, media_type, file_path, filename, ts))
    conn.commit()
    conn.close()

def get_media_records(device_id=None, media_type=None, limit=50):
    conn = get_db()
    cursor = conn.cursor()
    if device_id and media_type:
        cursor.execute("""
            SELECT * FROM media_records WHERE device_id = ? AND media_type = ? ORDER BY id DESC LIMIT ?
        """, (device_id, media_type, limit))
    elif device_id:
        cursor.execute("""
            SELECT * FROM media_records WHERE device_id = ? ORDER BY id DESC LIMIT ?
        """, (device_id, limit))
    elif media_type:
        cursor.execute("""
            SELECT * FROM media_records WHERE media_type = ? ORDER BY id DESC LIMIT ?
        """, (media_type, limit))
    else:
        cursor.execute("""
            SELECT * FROM media_records ORDER BY id DESC LIMIT ?
        """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ========== जिओफेन्स मॅनेजमेंट ==========

def add_geofence(device_id, name, lat, lon, radius_meters=200):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO geofences (device_id, name, latitude, longitude, radius_meters)
        VALUES (?, ?, ?, ?, ?)
    """, (device_id, name, float(lat), float(lon), float(radius_meters)))
    conn.commit()
    conn.close()

def get_geofences(device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM geofences WHERE device_id = ?", (device_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_geofence(fence_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM geofences WHERE id = ?", (fence_id,))
    conn.commit()
    conn.close()

# ========== अलर्ट्स आणि SOS ==========

def add_alert(device_id, alert_type, message, lat=None, lon=None):
    conn = get_db()
    cursor = conn.cursor()
    now_ts = now_str()

    # वारंवार स्पॅम न होण्यासाठी सक्रिय अलर्ट तपासणे
    if alert_type in ["LOW_BATTERY", "GEOFENCE_EXIT"]:
        cursor.execute("""
            SELECT id FROM alerts 
            WHERE device_id = ? AND alert_type = ? AND is_resolved = 0
        """, (device_id, alert_type))
        if cursor.fetchone():
            conn.close()
            return

    cursor.execute("""
        INSERT INTO alerts (device_id, alert_type, message, latitude, longitude, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (device_id, alert_type, message, lat, lon, now_ts))
    conn.commit()
    conn.close()

def get_active_alerts(limit=20):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.*, d.name as device_name
        FROM alerts a
        LEFT JOIN devices d ON a.device_id = d.id
        WHERE a.is_resolved = 0
        ORDER BY a.id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def resolve_alert(alert_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE alerts SET is_resolved = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def resolve_all_alerts():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE alerts SET is_resolved = 1 WHERE is_resolved = 0")
    conn.commit()
    conn.close()
