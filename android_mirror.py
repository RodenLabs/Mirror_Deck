"""
MirrorDeck v4 - Version limpia y verificada
- Puerto configurable
- Emparejamiento Android 11+
- Reinicio ADB que limpia entradas TLS duplicadas
- Audio del celular
- Instructivo completo integrado
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
import subprocess
import threading
import socket
import re
import sys
import os
import shutil
import time
import json
import zipfile
import tempfile
import urllib.request
import urllib.parse
import webbrowser
from pathlib import Path

CONFIG_FILE = Path.home() / ".mirrordeck_config.json"

# Ruta al ejecutable de adb. Por defecto asume que esta en el PATH, pero el
# instalador (install_gui.py) puede descargar un adb.exe portable y guardar
# su ruta completa en la config; en ese caso se actualiza este valor al
# arrancar la app (ver MirrorDeckApp.__init__).
ADB_BIN = "adb"

def app_dir() -> Path:
    """Carpeta donde vive el ejecutable (o el .py si corre desde el codigo
    fuente). Sirve para encontrar archivos externos junto al programa, como
    tap_mapper.apk, que el instalador copia al lado de MirrorDeck.exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(name) -> Path:
    """Ruta a un archivo empaquetado ADENTRO del .exe (via --add-data de
    PyInstaller), como el icono de la app. Distinto de app_dir(): los
    --add-data se extraen a una carpeta temporal (sys._MEIPASS) en modo
    --onefile, no a la carpeta donde vive el .exe."""
    base = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent)
    return base / name

# Tap Mapper: app Android aparte (proyecto "tap-mapper") que convierte
# botones de un joystick emparejado AL CELULAR (por bluetooth) en toques de
# pantalla, via un Servicio de Accesibilidad. Complementa al gamepad UHID de
# scrcpy (que requiere que el juego soporte control fisico): esto sirve para
# juegos que solo aceptan toques.
TAP_MAPPER_PKG     = "com.rodenapps.tapmapper"
TAP_MAPPER_SERVICE = f"{TAP_MAPPER_PKG}/.TapMapperAccessibilityService"
TAP_MAPPER_APK     = "tap_mapper.apk"

BG        = "#1a1a2e"
BG2       = "#16213e"
BG3       = "#0f3460"
BG4       = "#1a2744"
ACCENT2   = "#533483"
TEXT      = "#e0e0e0"
TEXT_DIM  = "#888888"
GREEN     = "#4ecca3"
YELLOW    = "#f5c518"
RED       = "#e94560"
ORANGE    = "#f5a623"
BLUE      = "#4a9eff"
FONT      = ("Segoe UI", 10)
FONT_B    = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 9)

IP_RE   = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
PORT_RE = re.compile(r"^\d{2,5}$")

FPS_OPTS  = ["30", "60", "120"]
BIT_OPTS  = ["2M", "4M", "8M", "16M", "32M"]
RES_OPTS  = ["480", "720", "1080", "1280", "1920", "0"]
COD_OPTS  = ["opus", "aac", "flac", "raw"]
VBUF_OPTS = ["0", "30", "50", "100", "200"]   # ms de buffer de video (anti-tartamudeo)
ABUF_OPTS = ["50", "100", "200", "400"]        # ms de buffer de audio (anti-tartamudeo)
# Codec que usa el codificador de HARDWARE del CELULAR (no tiene nada que
# ver con NVENC/AMF de la PC, eso es de OBS). h264 es el mas compatible,
# funciona en practicamente cualquier telefono. h265 pesa menos a igual
# calidad pero necesita un celular mas moderno. av1 es lo mas nuevo, solo
# en gama alta reciente.
VCOD_OPTS = ["h264", "h265", "av1"]

# Build "essentials" portátil de FFmpeg para Windows. Esta URL es fija
# (siempre apunta al build mas nuevo disponible), no a una version puntual.
# Solo se descarga si la persona activa "Incluir microfono de la PC" en
# Grabacion — no hace falta para el resto de la app.
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

FEEDBACK_EMAIL = "rodenlabsapps@gmail.com"

APP_VERSION        = "4.2.4"
TRIAL_DAYS         = 7
LICENSE_OFFLINE_GRACE_DAYS = 5   # dias que sigue andando sin poder validar online

# ── Actualizaciones (GitHub Releases) ───────────────────────────
# TODO: reemplazar por tu usuario/repo real de GitHub. Cada vez que
# compiles una version nueva, subila ahi como "Release" con un tag
# vX.Y.Z (ej. v4.1.0) y el .exe del instalador como archivo adjunto —
# la app compara sola su version contra la ultima publicada.
GITHUB_OWNER = "GrgicRoden"
GITHUB_REPO  = "Mirror_Deck"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# ── Licencia (Lemon Squeezy) ─────────────────────────────────────
# TODO: reemplazar los 3 valores de abajo una vez creada la tienda:
#  - LEMONSQUEEZY_STORE_URL: Store → tu producto → "Copy checkout URL"
#  - LEMONSQUEEZY_STORE_ID / LEMONSQUEEZY_PRODUCT_ID: numeros que
#    identifican TU tienda/producto (Settings → General para el Store
#    ID; la URL de edicion del producto trae el Product ID, ej.
#    app.lemonsqueezy.com/products/12345/edit → 12345).
# Estos dos ultimos son importantes: sin ellos, CUALQUIER clave de
# licencia valida de CUALQUIER producto de Lemon Squeezy (no solo el
# tuyo) activaria la app. Con ellos, se verifica que la clave
# pertenezca especificamente a tu producto.
LEMONSQUEEZY_STORE_URL     = "https://rodenlabs.lemonsqueezy.com/checkout/buy/8e7b1a32-e9d8-454a-847c-23f265429d14"
LEMONSQUEEZY_STORE_ID      = 450584
LEMONSQUEEZY_PRODUCT_ID    = 1285639
LEMONSQUEEZY_API_ACTIVATE  = "https://api.lemonsqueezy.com/v1/licenses/activate"
LEMONSQUEEZY_API_VALIDATE  = "https://api.lemonsqueezy.com/v1/licenses/validate"

CONTROL_HELP_TEXT = (
    "Iniciar Mirror: lanza scrcpy con toda la configuracion de abajo. "
    "Necesita un celular conectado y seleccionado en Paso 2.\n\n"
    "Detener Mirror: corta la ventana del espejo.\n\n"
    "'Como capturar en OBS' explica el paso a paso para agregar la "
    "ventana como fuente en OBS.\n\n"
    "'Instructivo completo' tiene la guia entera de la app, desde cero: "
    "activar depuracion inalambrica, emparejar, problemas comunes, etc. "
    "— todo esto tambien esta explicado seccion por seccion con los "
    "botones '?' que ves en cada recuadro de configuracion (mas abajo, "
    "con scroll)."
)

CONTROL_HELP_TEXT_EN = (
    "Start Mirror: launches scrcpy with all the settings below. "
    "Needs a phone connected and selected in Step 2.\n\n"
    "Stop Mirror: closes the mirror window.\n\n"
    "'How to capture in OBS' explains step by step how to add the "
    "window as a source in OBS.\n\n"
    "'Full guide' has the entire walkthrough of the app, from scratch: "
    "turning on wireless debugging, pairing, common issues, etc. "
    "— all of this is also explained section by section with the "
    "'?' buttons you see on each settings box (further down, "
    "scrollable)."
)

CONTROL_HELP_TEXT_PT = (
    "Iniciar Mirror: inicia o scrcpy com todas as configuracoes abaixo. "
    "Precisa de um celular conectado e selecionado no Passo 2.\n\n"
    "Parar Mirror: fecha a janela do espelho.\n\n"
    "'Como capturar no OBS' explica passo a passo como adicionar a "
    "janela como fonte no OBS.\n\n"
    "'Guia completo' tem o tutorial inteiro do app, do zero: "
    "ativar a depuracao sem fio, parear, problemas comuns, etc. "
    "— tudo isso tambem esta explicado secao por secao com os "
    "botoes '?' que voce ve em cada quadro de configuracao (mais "
    "abaixo, com rolagem)."
)


# ── ADB ──────────────────────────────────────────────────────────
def run_adb(args, timeout=12):
    try:
        cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        r  = subprocess.run([ADB_BIN] + args, capture_output=True, text=True,
                            timeout=timeout, creationflags=cf)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "ADB no encontrado"
    except subprocess.TimeoutExpired:
        return -2, "", "Timeout"
    except Exception as e:
        return -3, "", str(e)


def get_tls_entries():
    """Retorna lista de seriales TLS duplicados."""
    _, out, _ = run_adb(["devices"])
    entries = []
    for line in (out or "").split("\n")[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            if "_adb-tls" in serial or "adb-tls-connect" in serial:
                entries.append(serial)
    return entries


def mdns_discover(kind, timeout=6):
    """Busca celulares anunciandose en la red local vía mDNS.
    kind: 'pairing' (pantalla de 'Vincular con codigo') o 'connect'
    (Depuracion inalambrica ya activada). Devuelve una lista de dicts
    {name, ip, port}. Lista vacia si no se encontro nada o el mDNS no
    esta soportado por esta version de adb (fallback silencioso: el
    usuario siempre puede seguir cargando IP/puerto/codigo a mano)."""
    rc, out, err = run_adb(["mdns", "services"], timeout=timeout)
    if rc != 0:
        return []
    results = []
    tag = f"_adb-tls-{kind}._tcp"
    for line in (out or "").splitlines():
        line = line.strip()
        if tag not in line:
            continue
        m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d+)", line)
        if not m:
            continue
        ip, port = m.group(1), m.group(2)
        parts = line.split()
        name = parts[0] if parts else ip
        results.append({"name": name, "ip": ip, "port": port})
    return results


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "No disponible"


# ── FFMPEG (solo para mezclar microfono de la PC en la grabacion) ──
def ffmpeg_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return base / "MirrorDeck" / "ffmpeg"


def find_ffmpeg():
    d = ffmpeg_dir()
    if not d.exists():
        return None
    return next(d.rglob("ffmpeg.exe"), None)


def ensure_ffmpeg(log_cb=None):
    """Devuelve la ruta a ffmpeg.exe, descargandolo y descomprimiendolo la
    primera vez que haga falta (build portable de gyan.dev, ~90MB). Las
    veces siguientes lo encuentra ya instalado y no vuelve a descargar
    nada."""
    exe = find_ffmpeg()
    if exe:
        return str(exe)
    d = ffmpeg_dir()
    d.mkdir(parents=True, exist_ok=True)
    if log_cb:
        log_cb("→ Descargando FFmpeg (una sola vez, ~90MB)...")
    req = urllib.request.Request(FFMPEG_URL, headers={"User-Agent": "Mozilla/5.0"})
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "ffmpeg.zip"
        with urllib.request.urlopen(req, timeout=180) as resp, open(zip_path, "wb") as f:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                f.write(chunk)
        if log_cb:
            log_cb("→ Descomprimiendo FFmpeg...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(d)
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError("El paquete de FFmpeg descargado no contenia ffmpeg.exe")
    if log_cb:
        log_cb("✓ FFmpeg listo.")
    return str(exe)


def list_mic_devices(ffmpeg_path):
    """Lista los microfonos (dispositivos de audio DirectShow) que Windows
    tiene disponibles, usando el propio ffmpeg para consultarlos."""
    cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=15, creationflags=cf)
        out = r.stderr or r.stdout or ""
    except Exception:
        return []
    devices = []
    in_audio = False
    for line in out.splitlines():
        if "DirectShow audio devices" in line:
            in_audio = True
            continue
        if "DirectShow video devices" in line:
            in_audio = False
            continue
        if in_audio:
            m = re.search(r'"([^"]+)"', line)
            if m:
                devices.append(m.group(1))
    return devices


# ── APP ──────────────────────────────────────────────────────────
class MirrorDeckApp:
    def __init__(self, root):
        self.root         = root
        self.root.title(f"MirrorDeck v{APP_VERSION}")
        self.root.geometry("940x740")
        self.root.resizable(True, True)
        self.root.configure(bg=BG)
        self.root.minsize(800, 600)
        try:
            self.root.state("zoomed")  # arranca maximizada (Windows)
        except tk.TclError:
            pass

        # Icono de la ventana (esquina superior izquierda / barra de tareas).
        # Sin esto, Tkinter usa su icono default (la "pluma"). --icon de
        # PyInstaller solo pinta el .exe, no la ventana en tiempo de ejecucion.
        try:
            self.root.iconbitmap(default=str(resource_path("icon.ico")))
        except Exception:
            pass

        self.mirror_proc     = None
        self.mirror_active   = False
        self.devices         = []
        self.auto_job        = None
        self.connecting      = False
        self.pairing         = False
        self.restart_job     = None
        self.pending_restart = False
        self.mic_proc        = None
        self._rec_info       = None
        self._pending_update = None

        self.status_var    = tk.StringVar(value="Iniciando...")
        self.config        = self._load_config()
        self.lang          = self.config.get("language", "es")

        global ADB_BIN
        ADB_BIN = self.config.get("adb_path", "adb").strip() or "adb"

        # Primera vez que se abre la app: arranca la cuenta de la prueba
        # gratis. Se guarda directo (sin pasar por _save_config, que
        # todavia no puede correr aca porque depende de widgets que se
        # crean recien en _build_ui).
        if not self.config.get("first_run"):
            self.config["first_run"] = time.strftime("%Y-%m-%d")
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(self.config, f, indent=2)
            except Exception:
                pass

        self._build_ui()
        self._refresh_license_label()
        self.root.after(400, self._startup)
        self.root.after(700, self._maybe_show_changelog)
        self.root.after(1500, lambda: threading.Thread(
            target=self._validate_license_bg, daemon=True).start())
        self.root.after(3000, lambda: self._check_for_update(silent=True))

    # ── CONFIG ───────────────────────────────────────────────────
    def _load_config(self):
        defaults = {
            "last_ip": "", "last_port": "5555",
            "scrcpy_path": "scrcpy",
            "adb_path": "adb",
            "max_fps": "60", "bitrate": "8M", "resolution": "1280",
            "video_codec": "h264",
            "video_buffer": "50", "audio_buffer": "200",
            "audio_enabled": True, "audio_codec": "opus",
            "show_touches": False, "stay_awake": True,
            "borderless": True, "always_on_top": False,
            "window_title": "MirrorDeck",
            "profiles": {},
            "record_enabled": False,
            "record_dir": str(Path.home() / "Videos" / "MirrorDeck"),
            "mic_enabled": False,
            "mic_device": "",
            "first_run": "",
            "license_key": "",
            "license_instance_id": "",
            "license_last_ok": "",
            "language": "es",
            "pending_changelog_version": "",
            "pending_changelog_notes": "",
            "last_changelog_version": "",
            "last_changelog_notes": "",
        }
        # Migracion: si es la primera vez que corre con el nombre nuevo de
        # config (MirrorDeck) pero existe la config vieja de "Android
        # Mirror", la usamos como base en vez de arrancar de cero.
        old_config = Path.home() / ".android_mirror_config.json"
        if not CONFIG_FILE.exists() and old_config.exists():
            try:
                with open(old_config) as f:
                    defaults.update(json.load(f))
            except Exception:
                pass
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    defaults.update(json.load(f))
            except Exception:
                pass
        return defaults

    def _save_config(self):
        try:
            global ADB_BIN
            ADB_BIN = self.adb_path_var.get().strip() or "adb"
            self.config.update({
                "last_ip":       self.ip_var.get().strip(),
                "last_port":     self.port_var.get().strip() or "5555",
                "scrcpy_path":   self.scrcpy_var.get().strip(),
                "adb_path":      self.adb_path_var.get().strip() or "adb",
                "max_fps":       self.fps_var.get(),
                "bitrate":       self.bitrate_var.get(),
                "resolution":    self.res_var.get(),
                "video_codec":   self.vcodec_var.get(),
                "video_buffer":  self.vbuf_var.get(),
                "audio_buffer":  self.abuf_var.get(),
                "audio_enabled": self.chk_audio.get(),
                "audio_codec":   self.codec_var.get(),
                "show_touches":  self.chk_touches.get(),
                "stay_awake":    self.chk_awake.get(),
                "borderless":    self.chk_borderless.get(),
                "always_on_top": self.chk_ontop.get(),
                "window_title":  self.title_var.get().strip(),
                "gamepad_enabled": self.chk_gamepad.get(),
                "record_enabled": self.chk_record.get(),
                "record_dir":    self.record_dir_var.get().strip(),
                "mic_enabled":   self.chk_mic.get(),
                "mic_device":    self.mic_device_var.get(),
            })
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def _on_language_change(self, *_):
        sel = self.lang_var.get()
        new_lang = "pt" if sel == "PT" else ("en" if sel == "EN" else "es")
        self.config["language"] = new_lang
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass
        if new_lang != self.lang:
            messagebox.showinfo(
                self._h("Idioma", "Language", "Idioma"),
                self._h(
                    "Se guardo el idioma. Cerra y volve a abrir la app para "
                    "que se aplique en toda la interfaz.",
                    "Language saved. Close and reopen the app for it to "
                    "apply across the whole interface.",
                    "O idioma foi salvo. Feche e abra o app novamente para "
                    "que a mudanca seja aplicada em toda a interface."))

    # ── STARTUP ──────────────────────────────────────────────────
    def _startup(self):
        rc, out, _ = run_adb(["version"])
        if rc != 0:
            self._log(self._h("⚠ ADB no encontrado. Ejecuta el instalador de dependencias.",
                               "⚠ ADB not found. Run the dependency installer.",
                               "⚠ ADB nao encontrado. Execute o instalador de dependencias."))
            self._set_status(self._h("ADB no encontrado", "ADB not found", "ADB nao encontrado"), RED)
            return
        self._log(f"✓ {out.split(chr(10))[0]}")

        # Limpiar TLS al arrancar
        tls = get_tls_entries()
        if tls:
            self._log(self._h(f"→ Limpiando {len(tls)} entrada(s) TLS duplicada(s)...",
                               f"→ Clearing {len(tls)} duplicate TLS entry(ies)...",
                               f"→ Limpando {len(tls)} entrada(s) TLS duplicada(s)..."))
            for serial in tls:
                run_adb(["disconnect", serial])

        last_ip   = self.config.get("last_ip", "")
        last_port = self.config.get("last_port", "5555")
        if last_ip and IP_RE.match(last_ip):
            self._log(self._h(f"→ Reconectando a {last_ip}:{last_port}...",
                               f"→ Reconnecting to {last_ip}:{last_port}...",
                               f"→ Reconectando a {last_ip}:{last_port}..."))
            self._set_status(self._h(f"Reconectando a {last_ip}...", f"Reconnecting to {last_ip}...", f"Reconectando a {last_ip}..."), YELLOW)
            threading.Thread(
                target=self._connect_bg,
                args=(last_ip, last_port, True),
                daemon=True
            ).start()
        else:
            self.refresh_devices()

    # ── UI ───────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=BG3, pady=8)
        hdr.pack(fill="x")

        hdr_title_frame = tk.Frame(hdr, bg=BG3, cursor="hand2")
        hdr_title_frame.pack(side="left", padx=18)

        # Logo real (icon_40.png) si esta disponible; si no, cae al emoji
        # como respaldo para no dejar el header vacio.
        self.header_icon_img = None
        try:
            self.header_icon_img = tk.PhotoImage(file=str(resource_path("icon_40.png")))
        except Exception:
            self.header_icon_img = None

        if self.header_icon_img is not None:
            icon_lbl = tk.Label(hdr_title_frame, image=self.header_icon_img, bg=BG3)
            icon_lbl.pack(side="left", padx=(0, 8))
            icon_lbl.bind("<Button-1>", lambda e: self._show_about())
            title_text = f"MirrorDeck v{APP_VERSION}"
        else:
            title_text = f"📱  MirrorDeck v{APP_VERSION}"

        title_lbl = tk.Label(hdr_title_frame, text=title_text,
                 font=("Segoe UI", 15, "bold"), bg=BG3, fg=TEXT, cursor="hand2")
        title_lbl.pack(side="left")
        title_lbl.bind("<Button-1>", lambda e: self._show_about())
        tk.Button(hdr, text=self._h("ⓘ Acerca de", "ⓘ About", "ⓘ Sobre"),
                  command=self._show_about,
                  bg=BG3, fg=TEXT_DIM, activebackground=BG3, activeforeground=TEXT,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  cursor="hand2").pack(side="left", padx=(0, 18))

        hdr_right = tk.Frame(hdr, bg=BG3)
        hdr_right.pack(side="right", padx=18)
        self.status_hdr = tk.Label(hdr_right, textvariable=self.status_var,
                                    font=("Segoe UI", 9), bg=BG3, fg=TEXT_DIM)
        self.status_hdr.pack(side="right")
        tk.Button(hdr_right, text=self._h("⬇ Buscar actualizacion", "⬇ Check for update", "⬇ Buscar atualizacao"),
                  command=lambda: self._check_for_update(silent=False),
                  bg=BG3, fg=TEXT_DIM, activebackground=BG3, activeforeground=TEXT,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  cursor="hand2").pack(side="right", padx=(0, 16))

        # Aviso de actualizacion disponible: NO se empaqueta (no se ve)
        # hasta que _show_update_banner lo activa — nunca interrumpe con
        # un popup ni cierra la app sola, la persona hace click cuando
        # quiere (ver _check_for_update_bg).
        self.update_banner_lbl = tk.Label(hdr_right, text="", font=("Segoe UI", 8, "bold"),
                                           bg=BG3, fg=GREEN, cursor="hand2")
        self.update_banner_lbl.bind("<Button-1>", self._confirm_install_update)

        self.license_lbl = tk.Label(hdr_right, text="", font=("Segoe UI", 9),
                                     bg=BG3, fg=TEXT_DIM, cursor="hand2")
        self.license_lbl.pack(side="right", padx=(0, 16))
        self.license_lbl.bind("<Button-1>", lambda e: self._open_license_dialog())

        self.lang_var = tk.StringVar(
            value="PT" if self.lang == "pt" else ("EN" if self.lang == "en" else "ES"))
        lang_combo = ttk.Combobox(hdr_right, textvariable=self.lang_var,
                                   values=["ES", "EN", "PT"], width=4, state="readonly",
                                   font=("Segoe UI", 8))
        lang_combo.pack(side="right", padx=(0, 16))
        lang_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        # Barra de control FIJA: iniciar/detener mirror y los botones de
        # ayuda quedan siempre visibles, sin importar cuanto crezcan las
        # secciones de configuracion de abajo (que ahora tienen su propio
        # scroll). Antes esto vivia al final de la columna derecha y en
        # pantallas mas chicas (o con muchas secciones nuevas) quedaba
        # tapado/inalcanzable.
        ctrl = tk.Frame(self.root, bg=BG2)
        ctrl.pack(fill="x")
        tk.Frame(ctrl, bg=BG3, height=1).pack(fill="x")
        ctrl_in = tk.Frame(ctrl, bg=BG2, pady=6)
        ctrl_in.pack(fill="x")
        self.start_btn = self._btn(ctrl_in, self._h("▶  Iniciar Mirror", "▶  Start Mirror", "▶  Iniciar Mirror"),
                                    self._start_mirror, GREEN, big=True)
        self.start_btn.pack(side="left", padx=(12, 6))
        self.stop_btn = self._btn(ctrl_in, self._h("⏹  Detener Mirror", "⏹  Stop Mirror", "⏹  Parar Mirror"),
                                   self._stop_mirror, RED, big=True)
        self.stop_btn.pack(side="left", padx=(0, 12))
        self.stop_btn.config(state="disabled")
        self._btn(ctrl_in, self._h("ℹ  Como capturar en OBS", "ℹ  How to capture in OBS", "ℹ  Como capturar no OBS"),
                   self._obs_help).pack(side="left", padx=(0, 6))
        self._btn(ctrl_in, self._h("📋  Instructivo completo", "📋  Full guide", "📋  Guia completo"),
                   self._show_instructivo, BLUE).pack(side="left", padx=(0, 6))
        self._btn(ctrl_in, self._h("💬  Comentario / Reportar error", "💬  Feedback / Report a bug", "💬  Comentario / Reportar erro"),
                   self._open_feedback, YELLOW).pack(side="left")
        tk.Button(ctrl_in, text="?",
                  command=lambda: self._show_help(
                      self._h("Control", "Control", "Controle"),
                      self._h(CONTROL_HELP_TEXT, CONTROL_HELP_TEXT_EN, CONTROL_HELP_TEXT_PT)),
                  bg=BG2, fg=BLUE, activebackground=BG2, activeforeground=BLUE,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  cursor="hand2", padx=6).pack(side="right", padx=12)

        # Panel dividido: arriba la configuracion (con scroll propio),
        # abajo el log. La barra divisoria (sash) se puede arrastrar para
        # agrandar el log tanto como haga falta.
        paned = tk.PanedWindow(self.root, orient="vertical", bg=BG3,
                                sashwidth=6, sashrelief="flat",
                                bd=0, showhandle=False)
        paned.pack(fill="both", expand=True)

        # Columnas (arriba), dentro de un canvas con scroll vertical
        # propio: si el contenido crece mas alto que la pantalla, nunca
        # queda nada inalcanzable, simplemente aparece la scrollbar.
        settings_wrap = tk.Frame(paned, bg=BG)
        settings_canvas = tk.Canvas(settings_wrap, bg=BG, highlightthickness=0)
        settings_sb = tk.Scrollbar(settings_wrap, orient="vertical",
                                    command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=settings_sb.set)
        settings_sb.pack(side="right", fill="y")
        settings_canvas.pack(side="left", fill="both", expand=True)

        main = tk.Frame(settings_canvas, bg=BG)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main_win = settings_canvas.create_window((0, 0), window=main, anchor="nw")
        main.bind("<Configure>", lambda e: settings_canvas.configure(
            scrollregion=settings_canvas.bbox("all")))
        settings_canvas.bind("<Configure>",
            lambda e: settings_canvas.itemconfig(main_win, width=e.width))

        def _wheel(e):
            settings_canvas.yview_scroll(-1 * (e.delta // 120), "units")
        settings_canvas.bind("<Enter>", lambda e: settings_canvas.bind_all("<MouseWheel>", _wheel))
        settings_canvas.bind("<Leave>", lambda e: settings_canvas.unbind_all("<MouseWheel>"))

        left  = tk.Frame(main, bg=BG)
        right = tk.Frame(main, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=8)
        self._build_left(left)
        self._build_right(right)
        paned.add(settings_wrap, minsize=200, stretch="always")

        # Log (abajo)
        lf = tk.LabelFrame(paned, text=" Log ", bg=BG, fg=TEXT_DIM,
                            font=FONT, relief="flat", bd=1)
        self.log_box = scrolledtext.ScrolledText(
            lf, height=6, bg=BG2, fg=TEXT_DIM, font=FONT_MONO,
            state="disabled", relief="flat", insertbackground=TEXT)
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)
        paned.add(lf, minsize=90, stretch="always")

    def _h(self, es, en, pt=None):
        """Devuelve el texto en el idioma activo. Uso: self._h('texto ES',
        'texto EN', 'texto PT'). El idioma se fija al construir la UI
        (self.lang); un cambio de idioma pide reiniciar la app para tomar
        efecto en todos los widgets ya creados. Si falta la traduccion pt,
        cae a en como red de seguridad (no deberia pasar en la practica)."""
        if self.lang == "pt" and pt is not None:
            return pt
        return en if self.lang == "en" else es

    def _sec(self, parent, title, help_text=None):
        """Crea una seccion (LabelFrame). Si se pasa help_text, el titulo
        lleva al lado un boton '?' que abre un popup con instrucciones
        especificas de esa seccion — para que la ayuda este ahi mismo,
        en la app corriendo, sin tener que ir a buscar un README."""
        if not help_text:
            return tk.LabelFrame(parent, text=f" {title} ", bg=BG, fg=TEXT_DIM,
                                  font=FONT, relief="flat", bd=1,
                                  highlightbackground=BG3, highlightthickness=1)
        lblw = tk.Frame(parent, bg=BG)
        tk.Label(lblw, text=f" {title} ", bg=BG, fg=TEXT_DIM, font=FONT).pack(side="left")
        tk.Button(lblw, text="?", command=lambda: self._show_help(title, help_text),
                  bg=BG, fg=BLUE, activebackground=BG, activeforeground=BLUE,
                  font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                  cursor="hand2", padx=4, pady=0).pack(side="left")
        return tk.LabelFrame(parent, labelwidget=lblw, bg=BG, fg=TEXT_DIM,
                              font=FONT, relief="flat", bd=1,
                              highlightbackground=BG3, highlightthickness=1)

    def _show_help(self, title, text):
        win = tk.Toplevel(self.root)
        win.title(f"Ayuda · {title}")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        tk.Label(win, text=title, bg=BG, fg=TEXT, font=FONT_B).pack(
            padx=16, pady=(14, 6), anchor="w")
        tk.Label(win, text=text, bg=BG, fg=TEXT_DIM, font=FONT,
                 justify="left", wraplength=380).pack(padx=16, pady=(0, 6), anchor="w")
        tk.Button(win, text="Cerrar", command=win.destroy,
                   bg=BG3, fg=TEXT, relief="flat", font=FONT,
                   padx=20, pady=6, cursor="hand2").pack(pady=(4, 14))
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _maybe_show_changelog(self):
        """Si la app se acaba de auto-actualizar (ver _download_update_bg),
        muestra las notas de la version UNA sola vez al reabrir, despues
        las deja disponibles para consultar despues desde 'Acerca de'."""
        ver = self.config.get("pending_changelog_version", "")
        if not ver or ver != APP_VERSION:
            return
        notes = self.config.get("pending_changelog_notes", "")
        self.config["last_changelog_version"] = ver
        self.config["last_changelog_notes"] = notes
        self.config["pending_changelog_version"] = ""
        self.config["pending_changelog_notes"] = ""
        self._save_config()
        self._show_changelog_dialog(ver, notes)

    def _show_changelog_dialog(self, ver, notes):
        win = tk.Toplevel(self.root)
        win.title(self._h(f"Novedades de la version {ver}", f"What's new in version {ver}", f"Novidades da versao {ver}"))
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)

        tk.Label(win, text=self._h(f"✓ Actualizado a la version {ver}",
                                    f"✓ Updated to version {ver}",
                                    f"✓ Atualizado para a versao {ver}"),
                 bg=BG, fg=GREEN, font=FONT_B).pack(padx=24, pady=(20, 8))

        body = (notes or "").strip() or self._h(
            "(Sin notas para esta version.)", "(No notes for this version.)", "(Sem notas para esta versao.)")
        txt = scrolledtext.ScrolledText(win, width=54, height=10, bg=BG2, fg=TEXT,
                                         font=FONT, relief="flat", wrap="word")
        txt.insert("1.0", body)
        txt.config(state="disabled")
        txt.pack(padx=24, pady=(0, 12))

        tk.Button(win, text=self._h("Cerrar", "Close", "Fechar"), command=win.destroy,
                  bg=BG3, fg=TEXT, relief="flat", font=FONT,
                  padx=20, pady=6, cursor="hand2").pack(pady=(0, 16))

        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _show_about(self):
        win = tk.Toplevel(self.root)
        win.title(self._h("Acerca de", "About", "Sobre"))
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)

        about_title = tk.Frame(win, bg=BG)
        about_title.pack(padx=24, pady=(20, 2))
        if self.header_icon_img is not None:
            tk.Label(about_title, image=self.header_icon_img, bg=BG).pack(side="left", padx=(0, 8))
            title_txt = f"MirrorDeck v{APP_VERSION}"
        else:
            title_txt = f"📱  MirrorDeck v{APP_VERSION}"
        tk.Label(about_title, text=title_txt,
                 bg=BG, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(win, text=self._h("Un producto de Roden Labs", "A Roden Labs product", "Um produto da Roden Labs"),
                 bg=BG, fg=TEXT_DIM, font=FONT).pack(padx=24, pady=(0, 12))

        status, _ = self._license_status()
        lic_txt = {
            "trial":    self._h("Prueba gratis activa", "Free trial active", "Teste gratis ativo"),
            "licensed": self._h("Licencia activa", "License active", "Licenca ativa"),
            "expired":  self._h("Sin licencia / prueba vencida", "No license / trial expired", "Sem licenca / teste vencido"),
        }.get(status, status)
        tk.Label(win, text=lic_txt, bg=BG, fg=GREEN if status != "expired" else RED,
                 font=("Segoe UI", 9)).pack(padx=24, pady=(0, 12))

        site_lbl = tk.Label(win, text="mirrordeck.netlify.app", bg=BG, fg=BLUE,
                             font=("Segoe UI", 9, "underline"), cursor="hand2")
        site_lbl.pack(padx=24, pady=(0, 4))
        site_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://mirrordeck.netlify.app"))

        tk.Button(win, text=self._h("💬 Comentario / Reportar error", "💬 Feedback / Report a bug", "💬 Comentario / Reportar erro"),
                  command=lambda: (win.destroy(), self._open_feedback()),
                  bg=BG2, fg=YELLOW, activebackground=BG3, activeforeground=YELLOW,
                  font=FONT, relief="flat", cursor="hand2", padx=10, pady=4, bd=0).pack(padx=24, pady=(4, 12))

        last_ver = self.config.get("last_changelog_version", "")
        if last_ver:
            tk.Button(win, text=self._h(f"📋 Novedades de la v{last_ver}",
                                         f"📋 What's new in v{last_ver}",
                                         f"📋 Novidades da v{last_ver}"),
                      command=lambda: self._show_changelog_dialog(
                          last_ver, self.config.get("last_changelog_notes", "")),
                      bg=BG2, fg=BLUE, activebackground=BG3, activeforeground=BLUE,
                      font=FONT, relief="flat", cursor="hand2", padx=10, pady=4, bd=0).pack(padx=24, pady=(0, 12))

        tk.Label(win, text=f"© {time.strftime('%Y')} Roden Labs. "
                            + self._h("Todos los derechos reservados.", "All rights reserved.", "Todos os direitos reservados."),
                 bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).pack(padx=24, pady=(0, 4))

        tk.Label(win, text=self._h(
                     "Incluye scrcpy y adb (Genymobile / Google, licencia Apache 2.0).",
                     "Includes scrcpy and adb (Genymobile / Google, Apache 2.0 license).",
                     "Inclui scrcpy e adb (Genymobile / Google, licenca Apache 2.0)."),
                 bg=BG, fg=TEXT_DIM, font=("Segoe UI", 7), wraplength=320, justify="center").pack(
            padx=24, pady=(0, 4))

        tk.Button(win, text=self._h("Cerrar", "Close", "Fechar"), command=win.destroy,
                   bg=BG3, fg=TEXT, relief="flat", font=FONT,
                   padx=20, pady=6, cursor="hand2").pack(pady=(4, 16))

        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _btn(self, parent, text, cmd, color=TEXT, big=False):
        return tk.Button(parent, text=text, command=cmd,
                         bg=BG2, fg=color, activebackground=BG3, activeforeground=color,
                         font=FONT_B if big else FONT, relief="flat",
                         cursor="hand2", padx=10, pady=5 if big else 3, bd=0)

    def _combo(self, parent, var, values, width=10, editable=False):
        if not editable and var.get() not in values:
            var.set(values[0])
        cb = ttk.Combobox(parent, textvariable=var, values=values,
                          width=width, state="normal" if editable else "readonly",
                          font=FONT)
        cb.set(var.get())
        cb.bind("<<ComboboxSelected>>", lambda e: var.set(cb.get()))
        return cb

    def _build_left(self, parent):
        # ── Conexion WiFi
        s1 = self._sec(parent, self._h("Paso 1 · Conectar por WiFi", "Step 1 · Connect via WiFi", "Passo 1 · Conectar por WiFi"),
            self._h(
            "Conecta tu celular a MirrorDeck por WiFi (sin cable).\n\n"
            "Forma rapida: activa 'Depuracion inalambrica' en el celular "
            "(Ajustes → Opciones de desarrollador) y toca el boton "
            "'🔍 Buscar' de al lado — detecta la IP y el puerto solos, sin "
            "que tengas que ir a mirarlos en el celular.\n\n"
            "Forma manual (si 'Buscar' no encuentra nada):\n"
            "1. En el celular, con Depuracion inalambrica activada, toca "
            "el texto para ver la IP y el PUERTO.\n"
            "2. Escribi esa IP y puerto aca y toca 'Conectar'.\n"
            "3. Si es la primera vez (o si el celular pide emparejar de "
            "nuevo), primero usa la seccion 'Emparejar' de abajo.\n\n"
            "Sobre el puerto: cambia cada vez que activas Depuracion "
            "inalambrica de nuevo — es asi por seguridad de Android, no es "
            "un error de la app. Por eso conviene usar 'Buscar' en vez de "
            "tipearlo a mano cada vez. La IP en cambio suele quedar igual "
            "mientras no cambies de red WiFi.\n\n"
            "'Auto-conectar' intenta conectar solo apenas escribis una IP "
            "valida, sin que tengas que tocar el boton.\n"
            "'Reiniciar ADB' arregla la mayoria de los errores de "
            "conexion despues de reiniciar la PC.",

            "Connects your phone to MirrorDeck over WiFi (no cable).\n\n"
            "Fast way: turn on 'Wireless debugging' on the phone "
            "(Settings → Developer options) and tap the '🔍 Search' "
            "button right next to the fields — it detects the IP and "
            "port on its own, no need to go look them up on the phone.\n\n"
            "Manual way (if 'Search' doesn't find anything):\n"
            "1. On the phone, with Wireless debugging on, tap the text "
            "to see the IP and PORT.\n"
            "2. Type that IP and port here and tap 'Connect'.\n"
            "3. If it's the first time (or the phone asks to pair "
            "again), use the 'Pair' section below first.\n\n"
            "About the port: it changes every time you turn Wireless "
            "debugging back on — that's an Android security behavior, "
            "not a bug in the app. That's exactly why it's worth using "
            "'Search' instead of typing it in by hand each time. The IP, "
            "on the other hand, usually stays the same as long as you "
            "don't switch WiFi networks.\n\n"
            "'Auto-connect' tries to connect as soon as you type a "
            "valid IP, without having to press the button.\n"
            "'Restart ADB' fixes most connection errors after "
            "restarting the PC.",

            "Conecta seu celular ao MirrorDeck por WiFi (sem cabo).\n\n"
            "Forma rapida: ative a 'Depuracao sem fio' no celular "
            "(Configuracoes → Opcoes do desenvolvedor) e toque no botao "
            "'🔍 Buscar' ao lado — detecta o IP e a porta sozinho, sem "
            "precisar ir olhar no celular.\n\n"
            "Forma manual (se 'Buscar' nao encontrar nada):\n"
            "1. No celular, com a Depuracao sem fio ativada, toque no "
            "texto para ver o IP e a PORTA.\n"
            "2. Digite esse IP e porta aqui e toque em 'Conectar'.\n"
            "3. Se for a primeira vez (ou se o celular pedir para parear "
            "de novo), use primeiro a secao 'Parear' abaixo.\n\n"
            "Sobre a porta: ela muda toda vez que voce ativa a Depuracao "
            "sem fio de novo — isso e um comportamento de seguranca do "
            "Android, nao e um erro do app. Por isso vale mais a pena usar "
            "'Buscar' do que digitar na mao toda vez. Ja o IP costuma "
            "ficar igual enquanto voce nao trocar de rede WiFi.\n\n"
            "'Auto-conectar' tenta conectar assim que voce digita um IP "
            "valido, sem precisar tocar no botao.\n"
            "'Reiniciar ADB' resolve a maioria dos erros de conexao "
            "depois de reiniciar o PC."))
        s1.pack(fill="x", pady=(0, 8))

        tk.Label(s1, text=self._h("IP de tu PC:", "Your PC's IP:", "IP do seu PC:"), bg=BG, fg=TEXT_DIM, font=FONT).grid(
            row=0, column=0, sticky="w", padx=8, pady=3)
        tk.Label(s1, text=get_local_ip(), bg=BG, fg=GREEN, font=FONT).grid(
            row=0, column=1, columnspan=3, sticky="w")

        tk.Label(s1, text=self._h("IP del celular:", "Phone IP:", "IP do celular:"), bg=BG, fg=TEXT, font=FONT).grid(
            row=1, column=0, sticky="w", padx=8, pady=3)
        self.ip_var = tk.StringVar(value=self.config.get("last_ip", ""))
        tk.Entry(s1, textvariable=self.ip_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat", width=16).grid(
            row=1, column=1, padx=4, pady=3, sticky="w")

        tk.Label(s1, text=self._h("Puerto:", "Port:", "Porta:"), bg=BG, fg=TEXT, font=FONT).grid(
            row=1, column=2, sticky="w", padx=(8, 2))
        self.port_var = tk.StringVar(value=self.config.get("last_port", "5555"))
        tk.Entry(s1, textvariable=self.port_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat", width=7).grid(
            row=1, column=3, padx=4, pady=3, sticky="w")

        self.search_connect_btn = self._btn(
            s1, self._h("🔍 Buscar", "🔍 Search", "🔍 Buscar"),
            self._search_connect_device, BLUE)
        self.search_connect_btn.grid(row=1, column=4, padx=(6, 0), pady=3, sticky="w")

        tk.Label(s1, text=self._h(
                  "(o toca 'Buscar' para detectarlo solo en la red)",
                  "(or tap 'Search' to auto-detect it on the network)",
                  "(ou toque 'Buscar' para detectar sozinho na rede)"),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).grid(
            row=2, column=0, columnspan=5, sticky="w", padx=8)

        self.auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(s1, text=self._h(
                       "Auto-conectar al escribir IP valida",
                       "Auto-connect when a valid IP is typed",
                       "Auto-conectar ao digitar um IP valido"),
                       variable=self.auto_var, bg=BG, fg=TEXT_DIM,
                       selectcolor=BG3, activebackground=BG,
                       font=("Segoe UI", 8)).grid(
            row=3, column=0, columnspan=4, sticky="w", padx=8)
        self.ip_var.trace_add("write", self._on_ip_change)

        bf = tk.Frame(s1, bg=BG)
        bf.grid(row=4, column=0, columnspan=4, pady=5, padx=8, sticky="w")
        self.connect_btn = self._btn(bf, self._h("⚡ Conectar", "⚡ Connect", "⚡ Conectar"), self._connect_manual, GREEN)
        self.connect_btn.pack(side="left", padx=(0, 5))
        self._btn(bf, self._h("✕ Desconectar", "✕ Disconnect", "✕ Desconectar"), self._disconnect, RED).pack(side="left", padx=(0, 5))
        self._btn(bf, self._h("↺ Reiniciar ADB", "↺ Restart ADB", "↺ Reiniciar ADB"), self._restart_adb, YELLOW).pack(side="left", padx=(0, 5))
        self._btn(bf, self._h("🚪 Olvidar dispositivo", "🚪 Forget device", "🚪 Esquecer dispositivo"), self._forget_device, YELLOW).pack(side="left")

        self.conn_lbl = tk.Label(s1, text=self._h("● Sin conexion", "● No connection", "● Sem conexao"), bg=BG,
                                  fg=TEXT_DIM, font=("Segoe UI", 9))
        self.conn_lbl.grid(row=5, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 5))

        # ── Emparejamiento
        sp = self._sec(parent, self._h(
            "Emparejar  (normalmente 1 vez · Android 11+)",
            "Pair  (usually once · Android 11+)",
            "Parear  (normalmente 1 vez · Android 11+)"),
            self._h(
            "En teoria hace falta UNA sola vez por celular. En la "
            "practica, algunos celulares con Android modificado por el "
            "fabricante (Xiaomi, Oppo, Vivo, Huawei y en general marcas "
            "chinas menos conocidas) 'olvidan' el emparejamiento si "
            "Depuracion inalambrica estuvo apagada un rato, o al reiniciar "
            "el celular — ahi hay que repetir estos pasos de nuevo. "
            "¿Como saber si el tuyo es de estos? Fijate en Ajustes → "
            "Acerca del telefono si aparece un nombre de capa propia "
            "(MIUI, ColorOS, Funtouch OS, EMUI, etc.) — cuanto mas "
            "personalizada la marca, mas probable que pase esto. Si la "
            "conexion de arriba empieza a fallar despues de haber andado "
            "bien, proba emparejar de nuevo antes de asumir que algo se "
            "rompio.\n\n"
            "1. En el celular: Depuracion inalambrica → 'Vincular con "
            "codigo de vinculacion'.\n"
            "2. Aparece un codigo de 6 digitos y un PUERTO DE VINCULACION "
            "(distinto al puerto de conexion normal, y que tambien cambia "
            "cada vez).\n"
            "3. Cargalo aca (o toca '🔍 Buscar' para completar la IP y el "
            "puerto solos): IP del celular, el puerto de vinculacion, y "
            "el codigo.\n"
            "4. Toca 'Emparejar'. Si dice 'Emparejado correctamente', ya "
            "podes conectar arriba con el puerto de DEPURACION (no el de "
            "vinculacion, son distintos).\n\n"
            "Truco para que pase menos seguido: deja 'Depuracion "
            "inalambrica' ACTIVADA todo lo que puedas en vez de apagarla, "
            "y sacale la optimizacion de bateria a ese servicio (ver "
            "'Problemas comunes' en el Instructivo completo) — apagar el "
            "interruptor es lo que mas gatilla que haya que re-emparejar.",

            "In theory you only need to do this ONCE per phone. In "
            "practice, some phones with manufacturer-modified Android "
            "(Xiaomi, Oppo, Vivo, Huawei, and Chinese brands in general) "
            "'forget' the pairing if Wireless debugging was off for a "
            "while, or after restarting the phone — in that case you "
            "have to repeat these steps again. How do you know if yours "
            "is one of these? Check Settings → About phone for a custom "
            "skin name (MIUI, ColorOS, Funtouch OS, EMUI, etc.) — the "
            "more customized the brand, the more likely this happens. If "
            "the connection above starts failing after working fine, try "
            "pairing again before assuming something broke.\n\n"
            "1. On the phone: Wireless debugging → 'Pair device with "
            "pairing code'.\n"
            "2. A 6-digit code and a PAIRING PORT appear (different from "
            "the normal connection port, and it also changes every "
            "time).\n"
            "3. Enter it here (or tap '🔍 Search' to auto-fill the IP and "
            "port): phone IP, the pairing port, and the code.\n"
            "4. Tap 'Pair'. If it says 'Paired successfully', you can "
            "now connect above using the DEBUGGING port (not the "
            "pairing one, they're different).\n\n"
            "Tip to make this happen less often: leave 'Wireless "
            "debugging' ON as much as possible instead of turning it "
            "off, and remove battery optimization for that service (see "
            "'Common issues' in the Full guide) — turning the switch off "
            "is what most often triggers needing to re-pair.",

            "Em teoria, so precisa ser feito UMA vez por celular. Na "
            "pratica, alguns celulares com Android modificado pelo "
            "fabricante (Xiaomi, Oppo, Vivo, Huawei e marcas chinesas "
            "menos conhecidas em geral) 'esquecem' o pareamento se a "
            "Depuracao sem fio ficou desligada por um tempo, ou ao "
            "reiniciar o celular — nesse caso e preciso repetir esses "
            "passos de novo. Como saber se o seu e assim? Veja em "
            "Configuracoes → Sobre o telefone se aparece um nome de "
            "interface propria (MIUI, ColorOS, Funtouch OS, EMUI, etc.) "
            "— quanto mais personalizada a marca, mais provavel que isso "
            "aconteca. Se a conexao acima comecar a falhar depois de ter "
            "funcionado bem, tente parear de novo antes de supor que "
            "algo quebrou.\n\n"
            "1. No celular: Depuracao sem fio → 'Parear dispositivo com "
            "codigo de pareamento'.\n"
            "2. Aparece um codigo de 6 digitos e uma PORTA DE PAREAMENTO "
            "(diferente da porta de conexao normal, e que tambem muda "
            "toda vez).\n"
            "3. Preencha aqui (ou toque em '🔍 Buscar' para preencher o IP "
            "e a porta sozinho): IP do celular, a porta de pareamento e o "
            "codigo.\n"
            "4. Toque em 'Parear'. Se aparecer 'Pareado com sucesso', ja "
            "pode conectar acima usando a porta de DEPURACAO (nao a de "
            "pareamento, sao diferentes).\n\n"
            "Dica para que isso aconteca menos: deixe a 'Depuracao sem "
            "fio' LIGADA o maximo possivel em vez de desligar, e remova "
            "a otimizacao de bateria desse servico (veja 'Problemas "
            "comuns' no Guia completo) — desligar o interruptor e o que "
            "mais provoca a necessidade de parear de novo."))
        sp.pack(fill="x", pady=(0, 8))

        info = tk.Frame(sp, bg=BG4, pady=8, padx=10)
        info.pack(fill="x", padx=8, pady=(4, 6))
        tk.Label(info,
                  text=self._h(
                       "En el celu: Depuracion inalambrica\n"
                       "→ 'Vincular con codigo de vinculacion'\n"
                       "Ingresa la IP, el PUERTO de vinculacion y el CODIGO.",
                       "On the phone: Wireless debugging\n"
                       "→ 'Pair device with pairing code'\n"
                       "Enter the IP, the pairing PORT and the CODE.",
                       "No celular: Depuracao sem fio\n"
                       "→ 'Parear dispositivo com codigo de pareamento'\n"
                       "Digite o IP, a PORTA de pareamento e o CODIGO."),
                  bg=BG4, fg=TEXT_DIM, font=("Segoe UI", 8), justify="left").pack(anchor="w")

        pf = tk.Frame(sp, bg=BG)
        pf.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(pf, text="IP:", bg=BG, fg=TEXT, font=FONT).grid(
            row=0, column=0, sticky="w", pady=3)
        self.pair_ip_var = tk.StringVar(value=self.config.get("last_ip", ""))
        tk.Entry(pf, textvariable=self.pair_ip_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat", width=14).grid(
            row=0, column=1, padx=4, pady=3)

        tk.Label(pf, text=self._h("Puerto vinc.:", "Pairing port:", "Porta de pareamento:"), bg=BG, fg=TEXT, font=FONT).grid(
            row=0, column=2, sticky="w", padx=(8, 2))
        self.pair_port_var = tk.StringVar()
        tk.Entry(pf, textvariable=self.pair_port_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat", width=7).grid(
            row=0, column=3, padx=4, pady=3)

        self.search_pair_btn = self._btn(
            pf, self._h("🔍 Buscar", "🔍 Search", "🔍 Buscar"),
            self._search_pair_device, BLUE)
        self.search_pair_btn.grid(row=0, column=4, padx=(6, 0), pady=3, sticky="w")

        tk.Label(pf, text=self._h("Codigo:", "Code:", "Codigo:"), bg=BG, fg=TEXT, font=FONT).grid(
            row=1, column=0, sticky="w", pady=3)
        self.pair_code_var = tk.StringVar()
        tk.Entry(pf, textvariable=self.pair_code_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat", width=10).grid(
            row=1, column=1, padx=4, pady=3)
        self.pair_btn = self._btn(pf, self._h("Emparejar", "Pair", "Parear"), self._do_pair, ORANGE)
        self.pair_btn.grid(row=1, column=2, columnspan=2, padx=(8, 0), pady=3)

        tk.Label(pf, text=self._h(
                  "IP y puerto se completan solos con 'Buscar' — el codigo hay que leerlo del celu.",
                  "IP and port fill in automatically with 'Search' — the code still needs to be read from the phone.",
                  "IP e porta sao preenchidos com 'Buscar' — o codigo precisa ser lido no celular."),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8), wraplength=340, justify="left").grid(
            row=2, column=0, columnspan=5, sticky="w", padx=0, pady=(2, 0))

        self.pair_lbl = tk.Label(sp, text="", bg=BG, fg=TEXT_DIM,
                                  font=("Segoe UI", 8), wraplength=340, justify="left")
        self.pair_lbl.pack(padx=8, pady=(0, 6), anchor="w")

        # ── Dispositivos
        s2 = self._sec(parent, self._h("Paso 2 · Dispositivo", "Step 2 · Device", "Passo 2 · Dispositivo"),
            self._h(
            "Lista los celulares conectados por ADB (WiFi o USB). Se "
            "selecciona solo el primero de la lista al conectar.\n\n"
            "'Refrescar' vuelve a consultar la lista (util si conectaste "
            "otro celular o si no aparece el que esperabas).\n"
            "'Info del celular' te muestra la resolucion real, densidad, "
            "modelo y version de Android que reporta el celular — sirve "
            "para entender si un cambio de resolucion en la seccion Video "
            "va a tener efecto visible o no (si la resolucion elegida es "
            "mayor o igual a la nativa, no cambia nada, porque --max-size "
            "solo puede achicar la imagen, nunca agrandarla).",

            "Lists the phones connected via ADB (WiFi or USB). Only the "
            "first one in the list gets selected on connect.\n\n"
            "'Refresh' re-queries the list (useful if you connected "
            "another phone or the one you expected isn't showing).\n"
            "'Phone info' shows you the real resolution, density, model "
            "and Android version reported by the phone — useful to "
            "understand whether a resolution change in the Video section "
            "will have any visible effect (if the chosen resolution is "
            "greater than or equal to the native one, nothing changes, "
            "because --max-size can only shrink the image, never enlarge "
            "it).",

            "Lista os celulares conectados via ADB (WiFi ou USB). Apenas "
            "o primeiro da lista e selecionado ao conectar.\n\n"
            "'Atualizar' consulta a lista de novo (util se voce conectou "
            "outro celular ou se o que voce esperava nao aparece).\n"
            "'Info do celular' mostra a resolucao real, densidade, "
            "modelo e versao do Android informados pelo celular — serve "
            "para entender se uma mudanca de resolucao na secao Video "
            "vai ter efeito visivel ou nao (se a resolucao escolhida for "
            "maior ou igual a nativa, nada muda, porque --max-size so "
            "pode diminuir a imagem, nunca aumentar)."))
        s2.pack(fill="x", pady=(0, 8))
        self.device_list = tk.Listbox(s2, bg=BG2, fg=TEXT, selectbackground=ACCENT2,
                                       font=FONT_MONO, height=3, relief="flat",
                                       activestyle="none")
        self.device_list.pack(fill="x", padx=8, pady=4)
        self.device_list.bind("<<ListboxSelect>>", self._on_device_select)
        self.selected_serial = tk.StringVar()
        self.selected_lbl = tk.Label(s2, text=self._h("Seleccionado: —", "Selected: —", "Selecionado: —"),
                                      bg=BG, fg=TEXT_DIM, font=("Segoe UI", 9))
        self.selected_lbl.pack(padx=8, anchor="w")
        s2_btns = tk.Frame(s2, bg=BG)
        s2_btns.pack(padx=8, pady=(4, 6), anchor="w")
        self._btn(s2_btns, self._h("↻ Refrescar", "↻ Refresh", "↻ Atualizar"), self.refresh_devices,
                   color=YELLOW).pack(side="left", padx=(0, 6))
        self._btn(s2_btns, self._h("ℹ Info del celular", "ℹ Phone info", "ℹ Info do celular"), self._device_info,
                   color=BLUE).pack(side="left")

    def _build_right(self, parent):
        # ── Perfiles
        spf = self._sec(parent, self._h("Perfiles", "Profiles", "Perfis"),
            self._h(
            "Guarda hasta 4 combinaciones de configuracion con nombre "
            "(ej. 'Streaming', 'WhatsApp liviano') para cambiar todo de "
            "una sola vez en vez de retocar cada ajuste a mano.\n\n"
            "Elegi un perfil de la lista para aplicarlo al toque. "
            "'Guardar' toma la configuracion actual de Video/Audio/"
            "Ventana y la guarda con el nombre que le pongas (si ya "
            "existe ese nombre, lo actualiza).\n\n"
            "No incluye IP/puerto ni las rutas de scrcpy/adb — eso queda "
            "igual sin importar el perfil.",

            "Save up to 4 named settings combinations (e.g. 'Streaming', "
            "'Light WhatsApp') to switch everything at once instead of "
            "tweaking each setting by hand.\n\n"
            "Pick a profile from the list to apply it instantly. "
            "'Save' takes the current Video/Audio/Window settings and "
            "stores them under the name you give it (if that name "
            "already exists, it gets updated).\n\n"
            "Doesn't include IP/port or the scrcpy/adb paths — those "
            "stay the same regardless of the profile.",

            "Salva ate 4 combinacoes de configuracao com nome "
            "(ex. 'Streaming', 'WhatsApp leve') para trocar tudo de uma "
            "vez em vez de ajustar cada opcao na mao.\n\n"
            "Escolha um perfil da lista para aplica-lo na hora. "
            "'Salvar' pega a configuracao atual de Video/Audio/Janela e "
            "guarda com o nome que voce der (se esse nome ja existir, "
            "ele e atualizado).\n\n"
            "Nao inclui IP/porta nem os caminhos do scrcpy/adb — isso "
            "fica igual independente do perfil."))
        spf.pack(fill="x", pady=(0, 8))
        self.profile_var = tk.StringVar()
        prow = tk.Frame(spf, bg=BG)
        prow.pack(fill="x", padx=8, pady=(4, 2))
        self.profile_combo = ttk.Combobox(
            prow, textvariable=self.profile_var,
            values=list(self.config.get("profiles", {}).keys()),
            width=20, state="readonly", font=FONT)
        self.profile_combo.pack(side="left", padx=(0, 6))
        self.profile_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self._load_profile(self.profile_var.get()))
        prow2 = tk.Frame(spf, bg=BG)
        prow2.pack(fill="x", padx=8, pady=(2, 6))
        self._btn(prow2, self._h("💾 Guardar", "💾 Save", "💾 Salvar"), self._save_profile, GREEN).pack(
            side="left", padx=(0, 6))
        self._btn(prow2, self._h("🗑 Borrar", "🗑 Delete", "🗑 Excluir"), self._delete_profile, RED).pack(side="left")

        # ── Video
        sv = self._sec(parent, "Video",
            self._h(
            "FPS maximo: cuadros por segundo del mirror. 60 es un buen "
            "default; 30 pesa menos si tenes WiFi debil.\n\n"
            "Bitrate: calidad de imagen. Mas alto = mejor calidad pero mas "
            "datos por segundo (importante si el WiFi anda justo).\n\n"
            "Resolucion: limite MAXIMO del lado MAS LARGO de la pantalla "
            "(no del ancho). Ojo: un celular en vertical tiene el lado "
            "largo en la ALTURA, no en el ancho — ej. un celular de "
            "1080x2408 tiene el lado largo en 2408, entonces poniendo "
            "Resolucion en 1080 estas recortando bastante mas de lo que "
            "parece. Solo puede achicar, nunca agranda mas alla de lo que "
            "el celular ya tiene — usa 'Info del celular' (Paso 2) para "
            "ver el lado largo real y una recomendacion concreta.\n\n"
            "Codec: lo codifica el CELULAR, no la PC (no tiene nada que "
            "ver con NVENC de OBS). h264 anda en cualquier telefono; h265 "
            "pesa menos a igual calidad pero pide un celular mas moderno; "
            "av1 solo en gama alta muy reciente. Si el mirror no arranca "
            "despues de cambiarlo, tu celular no soporta ese codec — "
            "volve a h264.\n\n"
            "Buffer video: si hay tartamudeo/saltos, subilo (agrega un "
            "poquito de latencia a cambio de estabilidad). El desplegable "
            "trae valores comunes, pero podes ESCRIBIR cualquier numero a "
            "mano (ej. 60, 70, 75) si necesitas afinar entre dos — hace "
            "click adentro del campo y escribi el valor en ms.\n\n"
            "Los cambios de esta seccion reinician el mirror solo si ya "
            "esta activo.",

            "Max FPS: frames per second of the mirror. 60 is a good "
            "default; 30 uses less bandwidth if your WiFi is weak.\n\n"
            "Bitrate: image quality. Higher = better quality but more "
            "data per second (important if WiFi is tight).\n\n"
            "Resolution: MAXIMUM limit of the LONGER side of the screen "
            "(not the width). Watch out: a phone in portrait has its "
            "long side in HEIGHT, not width — e.g. a 1080x2408 phone has "
            "its long side at 2408, so setting Resolution to 1080 crops "
            "a lot more than it looks like. It can only shrink, never "
            "enlarge beyond what the phone already has — use 'Phone "
            "info' (Step 2) to see the real long side and a concrete "
            "recommendation.\n\n"
            "Codec: encoded by the PHONE, not the PC (unrelated to "
            "OBS's NVENC). h264 works on any phone; h265 is lighter at "
            "the same quality but needs a more modern phone; av1 only on "
            "very recent high-end phones. If the mirror doesn't start "
            "after changing it, your phone doesn't support that codec — "
            "go back to h264.\n\n"
            "Video buffer: if there's stuttering/skipping, raise it "
            "(adds a bit of latency in exchange for stability). The "
            "dropdown has common values, but you can TYPE any number by "
            "hand (e.g. 60, 70, 75) if you need to fine-tune between two "
            "— click inside the field and type the value in ms.\n\n"
            "Changes in this section restart the mirror only if it's "
            "already active.",

            "FPS maximo: quadros por segundo do mirror. 60 e um bom "
            "padrao; 30 consome menos dados se seu WiFi for fraco.\n\n"
            "Bitrate: qualidade de imagem. Mais alto = melhor qualidade "
            "mas mais dados por segundo (importante se o WiFi estiver "
            "no limite).\n\n"
            "Resolucao: limite MAXIMO do lado MAIS LONGO da tela (nao da "
            "largura). Atencao: um celular na vertical tem o lado longo "
            "na ALTURA, nao na largura — ex. um celular de 1080x2408 tem "
            "o lado longo em 2408, entao colocar Resolucao em 1080 corta "
            "bem mais do que parece. So pode diminuir, nunca aumenta "
            "alem do que o celular ja tem — use 'Info do celular' "
            "(Passo 2) para ver o lado longo real e uma recomendacao "
            "concreta.\n\n"
            "Codec: codificado pelo CELULAR, nao pelo PC (nao tem nada a "
            "ver com o NVENC do OBS). h264 funciona em qualquer "
            "telefone; h265 pesa menos com a mesma qualidade mas exige "
            "um celular mais moderno; av1 so em modelos topo de linha "
            "bem recentes. Se o mirror nao iniciar depois de trocar, seu "
            "celular nao suporta esse codec — volte para h264.\n\n"
            "Buffer de video: se houver engasgos/travadas, aumente "
            "(adiciona um pouco de latencia em troca de estabilidade). O "
            "menu suspenso traz valores comuns, mas voce pode DIGITAR "
            "qualquer numero a mao (ex. 60, 70, 75) se precisar ajustar "
            "entre dois valores — clique dentro do campo e digite o "
            "valor em ms.\n\n"
            "As mudancas nesta secao reiniciam o mirror somente se ele "
            "ja estiver ativo."))
        sv.pack(fill="x", pady=(0, 8))
        self.fps_var     = tk.StringVar(value=self.config.get("max_fps",    "60"))
        self.bitrate_var = tk.StringVar(value=self.config.get("bitrate",    "8M"))
        self.res_var     = tk.StringVar(value=self.config.get("resolution", "1280"))
        self.vbuf_var    = tk.StringVar(value=self.config.get("video_buffer", "50"))
        self.vcodec_var  = tk.StringVar(value=self.config.get("video_codec", "h264"))
        for i, (lbl, var, opts, editable) in enumerate([
            (self._h("FPS maximo:", "Max FPS:", "FPS maximo:"),    self.fps_var,     FPS_OPTS, False),
            (self._h("Bitrate:", "Bitrate:", "Bitrate:"),       self.bitrate_var,  BIT_OPTS, False),
            (self._h("Resolucion px:", "Resolution px:", "Resolucao px:"), self.res_var,      RES_OPTS, False),
            (self._h("Codec video:", "Video codec:", "Codec de video:"),   self.vcodec_var,   VCOD_OPTS, False),
            (self._h("Buffer video (ms):", "Video buffer (ms):", "Buffer de video (ms):"), self.vbuf_var, VBUF_OPTS, True),
        ]):
            tk.Label(sv, text=lbl, bg=BG, fg=TEXT, font=FONT).grid(
                row=i, column=0, sticky="w", padx=8, pady=4)
            self._combo(sv, var, opts, 8, editable=editable).grid(
                row=i, column=1, padx=8, pady=4, sticky="w")
        tk.Label(sv, text=self._h(
                  "  (0 = resolucion original del celular)",
                  "  (0 = phone's original resolution)",
                  "  (0 = resolucao original do celular)"),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8)
        tk.Label(sv, text=self._h(
                  "  Codec: lo procesa el celular, no tiene relacion con NVENC de OBS",
                  "  Codec: processed by the phone, unrelated to OBS's NVENC",
                  "  Codec: processado pelo celular, sem relacao com o NVENC do OBS"),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=8)
        tk.Label(sv, text=self._h(
                  "  Buffer video: se puede escribir cualquier valor a mano (ej. 70)",
                  "  Video buffer: you can type any value by hand (e.g. 70)",
                  "  Buffer de video: pode digitar qualquer valor a mao (ex. 70)"),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).grid(
            row=7, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        tk.Label(sv, text=self._h(
                  "  Los cambios reinician el mirror automaticamente si esta activo",
                  "  Changes automatically restart the mirror if it's active",
                  "  As mudancas reiniciam o mirror automaticamente se estiver ativo"),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).grid(
            row=8, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))
        for v in (self.fps_var, self.bitrate_var, self.res_var, self.vbuf_var, self.vcodec_var):
            v.trace_add("write", self._on_setting_change)

        # ── Audio
        sa = self._sec(parent, self._h("Audio del celular", "Phone audio", "Audio do celular"),
            self._h(
            "Captura el audio que suena en el celular (Android 11+) y lo "
            "manda junto con el video, para que OBS lo levante como si "
            "fuera un microfono/dispositivo de audio mas.\n\n"
            "Codec: opus es el default recomendado (liviano y buena "
            "calidad). Si tenes problemas probá aac.\n\n"
            "Buffer: igual que el de video — si el audio suena "
            "distorsionado o 'robotico', subilo. Tambien se puede "
            "escribir un valor a mano (ej. 150) ademas de los del "
            "desplegable.",

            "Captures the audio playing on the phone (Android 11+) and "
            "sends it along with the video, so OBS can pick it up as if "
            "it were another microphone/audio device.\n\n"
            "Codec: opus is the recommended default (lightweight and "
            "good quality). If you have issues, try aac.\n\n"
            "Buffer: same as the video one — if the audio sounds "
            "distorted or 'robotic', raise it. You can also type a "
            "value by hand (e.g. 150) in addition to the dropdown ones.",

            "Captura o audio que toca no celular (Android 11+) e envia "
            "junto com o video, para que o OBS reconheca como se fosse "
            "mais um microfone/dispositivo de audio.\n\n"
            "Codec: opus e o padrao recomendado (leve e boa qualidade). "
            "Se tiver problemas, tente aac.\n\n"
            "Buffer: igual ao do video — se o audio soar distorcido ou "
            "'robotico', aumente. Tambem da para digitar um valor a mao "
            "(ex. 150) alem dos do menu suspenso."))
        sa.pack(fill="x", pady=(0, 8))
        self.chk_audio = tk.BooleanVar(value=self.config.get("audio_enabled", True))
        tk.Checkbutton(sa, text=self._h(
                       "Capturar audio del celular (Android 11+)",
                       "Capture phone audio (Android 11+)",
                       "Capturar audio do celular (Android 11+)"),
                       variable=self.chk_audio, bg=BG, fg=TEXT,
                       selectcolor=BG3, activebackground=BG, font=FONT,
                       command=self._toggle_audio).pack(padx=8, pady=4, anchor="w")
        self.audio_f = tk.Frame(sa, bg=BG)
        self.audio_f.pack(fill="x", padx=20, pady=(0, 6))
        tk.Label(self.audio_f, text=self._h("Codec:", "Codec:", "Codec:"), bg=BG, fg=TEXT_DIM,
                  font=FONT).pack(side="left")
        self.codec_var = tk.StringVar(value=self.config.get("audio_codec", "opus"))
        self._combo(self.audio_f, self.codec_var, COD_OPTS, 8).pack(side="left", padx=8)
        tk.Label(self.audio_f, text=self._h("Buffer (ms):", "Buffer (ms):", "Buffer (ms):"), bg=BG, fg=TEXT_DIM,
                  font=FONT).pack(side="left", padx=(12, 0))
        self.abuf_var = tk.StringVar(value=self.config.get("audio_buffer", "200"))
        self._combo(self.audio_f, self.abuf_var, ABUF_OPTS, 6, editable=True).pack(side="left", padx=8)
        self._toggle_audio()
        tk.Label(sa, text=self._h(
                  "  Si el audio suena distorsionado/robotico, subi el buffer",
                  "  If the audio sounds distorted/robotic, raise the buffer",
                  "  Se o audio soar distorcido/robotico, aumente o buffer"),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).pack(padx=8, anchor="w")
        self.chk_audio.trace_add("write", self._on_setting_change)
        self.codec_var.trace_add("write", self._on_setting_change)
        self.abuf_var.trace_add("write", self._on_setting_change)

        # ── Ventana
        sw = self._sec(parent, self._h("Ventana", "Window", "Janela"),
            self._h(
            "Mostrar toques: dibuja un circulito en la pantalla del "
            "celular cada vez que se toca — util para tutoriales.\n\n"
            "Mantener pantalla encendida: evita que el celular se "
            "bloquee solo mientras el mirror esta activo.\n\n"
            "Sin bordes: saca la barra de titulo de Windows — mejor para "
            "capturar con OBS porque queda solo la pantalla del celular, "
            "sin recortar. Para mover la ventana sin bordes usa Windows + "
            "flecha (o destildá esta opcion para moverla con el mouse).\n\n"
            "Siempre visible: la ventana queda por encima de las demas.\n\n"
            "Titulo de ventana: el nombre que vas a buscar en OBS al "
            "agregar la 'Captura de ventana'.\n\n"
            "Rutas de scrcpy/adb: normalmente no hace falta tocarlas, el "
            "instalador las configura solas.",

            "Show touches: draws a small circle on the phone screen "
            "every time it's touched — useful for tutorials.\n\n"
            "Keep screen on: prevents the phone from locking itself "
            "while the mirror is active.\n\n"
            "Borderless: removes the Windows title bar — better for "
            "capturing with OBS because only the phone screen shows, "
            "with nothing cropped. To move a borderless window use "
            "Windows + arrow (or uncheck this option to move it with "
            "the mouse).\n\n"
            "Always on top: keeps the window above all others.\n\n"
            "Window title: the name you'll look for in OBS when adding "
            "'Window Capture'.\n\n"
            "scrcpy/adb paths: normally you don't need to touch these, "
            "the installer sets them up on its own.",

            "Mostrar toques: desenha um circulo na tela do celular toda "
            "vez que ela e tocada — util para tutoriais.\n\n"
            "Manter a tela ligada: evita que o celular bloqueie sozinho "
            "enquanto o mirror estiver ativo.\n\n"
            "Sem bordas: remove a barra de titulo do Windows — melhor "
            "para capturar com o OBS porque so fica a tela do celular, "
            "sem cortes. Para mover a janela sem bordas use Windows + "
            "seta (ou desmarque essa opcao para mover com o mouse).\n\n"
            "Sempre visivel: mantem a janela acima das outras.\n\n"
            "Titulo da janela: o nome que voce vai procurar no OBS ao "
            "adicionar a 'Captura de janela'.\n\n"
            "Caminhos do scrcpy/adb: normalmente nao precisa mexer, o "
            "instalador configura sozinho."))
        sw.pack(fill="x", pady=(0, 8))
        self.chk_touches    = tk.BooleanVar(value=self.config.get("show_touches",  False))
        self.chk_awake      = tk.BooleanVar(value=self.config.get("stay_awake",    True))
        self.chk_borderless = tk.BooleanVar(value=self.config.get("borderless",    True))
        self.chk_ontop      = tk.BooleanVar(value=self.config.get("always_on_top", False))
        cf = tk.Frame(sw, bg=BG)
        cf.pack(fill="x", padx=8, pady=4)
        for i, (var, lbl) in enumerate([
            (self.chk_touches,    self._h("Mostrar toques", "Show touches", "Mostrar toques")),
            (self.chk_awake,      self._h("Mantener pantalla encendida", "Keep screen on", "Manter tela ligada")),
            (self.chk_borderless, self._h("Sin bordes (mejor para OBS)", "Borderless (better for OBS)", "Sem bordas (melhor para OBS)")),
            (self.chk_ontop,      self._h("Siempre visible", "Always on top", "Sempre visivel")),
        ]):
            tk.Checkbutton(cf, text=lbl, variable=var, bg=BG, fg=TEXT,
                           selectcolor=BG3, activebackground=BG, font=FONT).grid(
                row=i // 2, column=i % 2, sticky="w", padx=4, pady=1)

        tk.Label(sw, text=self._h(
                  "  Sin bordes: mové la ventana con Windows + flecha",
                  "  Borderless: move the window with Windows + arrow",
                  "  Sem bordas: mova a janela com Windows + seta"),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).pack(padx=8, anchor="w")

        tk.Label(sw, text=self._h("Titulo ventana (para OBS):", "Window title (for OBS):", "Titulo da janela (para o OBS):"), bg=BG, fg=TEXT,
                  font=FONT).pack(padx=8, pady=(6, 0), anchor="w")
        self.title_var = tk.StringVar(value=self.config.get("window_title", "MirrorDeck"))
        tk.Entry(sw, textvariable=self.title_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat").pack(
            fill="x", padx=8, pady=(2, 4))

        tk.Label(sw, text=self._h("Ruta de scrcpy:", "scrcpy path:", "Caminho do scrcpy:"), bg=BG, fg=TEXT_DIM,
                  font=("Segoe UI", 8)).pack(padx=8, anchor="w")
        self.scrcpy_var = tk.StringVar(value=self.config.get("scrcpy_path", "scrcpy"))
        tk.Entry(sw, textvariable=self.scrcpy_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat").pack(
            fill="x", padx=8, pady=(2, 4))

        tk.Label(sw, text=self._h("Ruta de adb:", "adb path:", "Caminho do adb:"), bg=BG, fg=TEXT_DIM,
                  font=("Segoe UI", 8)).pack(padx=8, anchor="w")
        self.adb_path_var = tk.StringVar(value=self.config.get("adb_path", "adb"))
        tk.Entry(sw, textvariable=self.adb_path_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat").pack(
            fill="x", padx=8, pady=(2, 6))

        # ── Grabacion
        sr = self._sec(parent, self._h("Grabacion", "Recording", "Gravacao"),
            self._h(
            "Guarda una copia local del video y audio del celular mientras "
            "el mirror esta activo (ademas de mostrarlo en pantalla) — "
            "util para tener respaldo de un stream, o para grabar un "
            "tutorial sin depender de OBS.\n\n"
            "Se guarda como .mkv en la carpeta indicada, con fecha y hora "
            "en el nombre. Si cambias configuracion de Video/Audio "
            "mientras esta grabando, el archivo se corta y arranca uno "
            "nuevo (por el reinicio automatico de esa seccion).\n\n"
            "Incluir microfono de la PC: mezcla tu voz (u otro microfono) "
            "junto con el video y audio del celular en UN SOLO archivo "
            "final, no separado. La primera vez que la actives va a "
            "descargar FFmpeg (~90MB, una sola vez). Si queres los canales "
            "separados (voz aparte del audio del juego, por ejemplo), usa "
            "OBS en su lugar — esta funcion es a proposito todo-en-uno.",

            "Saves a local copy of the phone's video and audio while the "
            "mirror is active (in addition to showing it on screen) — "
            "useful as a backup of a stream, or to record a tutorial "
            "without relying on OBS.\n\n"
            "Saved as .mkv in the folder shown, with date and time in "
            "the name. If you change Video/Audio settings while "
            "recording, the file gets cut and a new one starts (because "
            "that section auto-restarts).\n\n"
            "Include PC microphone: mixes your voice (or another mic) "
            "together with the phone's video and audio into ONE final "
            "file, not separated. The first time you turn it on it will "
            "download FFmpeg (~90MB, once). If you want separate "
            "channels (voice apart from game audio, for example), use "
            "OBS instead — this feature is intentionally all-in-one.",

            "Salva uma copia local do video e audio do celular enquanto "
            "o mirror esta ativo (alem de mostrar na tela) — util para "
            "ter um backup de uma live, ou para gravar um tutorial sem "
            "depender do OBS.\n\n"
            "Salvo como .mkv na pasta indicada, com data e hora no "
            "nome. Se voce mudar a configuracao de Video/Audio enquanto "
            "esta gravando, o arquivo e cortado e um novo comeca (por "
            "causa do reinicio automatico dessa secao).\n\n"
            "Incluir microfone do PC: mistura sua voz (ou outro "
            "microfone) junto com o video e audio do celular em UM "
            "UNICO arquivo final, nao separado. Na primeira vez que "
            "ativar, vai baixar o FFmpeg (~90MB, uma unica vez). Se "
            "voce quiser os canais separados (voz separada do audio do "
            "jogo, por exemplo), use o OBS — esse recurso e "
            "propositalmente tudo-em-um."))
        sr.pack(fill="x", pady=(0, 8))
        self.chk_record = tk.BooleanVar(value=self.config.get("record_enabled", False))
        tk.Checkbutton(sr, text=self._h(
                       "Grabar copia local mientras el mirror esta activo",
                       "Record local copy while the mirror is active",
                       "Gravar copia local enquanto o mirror esta ativo"),
                       variable=self.chk_record, bg=BG, fg=TEXT,
                       selectcolor=BG3, activebackground=BG, font=FONT,
                       command=self._toggle_record).pack(
            padx=8, pady=4, anchor="w")
        rf = tk.Frame(sr, bg=BG)
        rf.pack(fill="x", padx=8, pady=(0, 6))
        self.record_dir_var = tk.StringVar(value=self.config.get(
            "record_dir", str(Path.home() / "Videos" / "MirrorDeck")))
        tk.Entry(rf, textvariable=self.record_dir_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat").pack(
            side="left", fill="x", expand=True)
        self._btn(rf, "📂", self._open_record_dir, TEXT_DIM).pack(side="left", padx=(6, 0))

        self.mic_f = tk.Frame(sr, bg=BG)
        self.mic_f.pack(fill="x", padx=8, pady=(2, 6))
        self.chk_mic = tk.BooleanVar(value=self.config.get("mic_enabled", False))
        self.mic_check = tk.Checkbutton(
            self.mic_f, text=self._h(
                "Incluir microfono de la PC (mezclado en el mismo archivo)",
                "Include PC microphone (mixed into the same file)",
                "Incluir microfone do PC (misturado no mesmo arquivo)"),
            variable=self.chk_mic, bg=BG, fg=TEXT, selectcolor=BG3,
            activebackground=BG, font=FONT, command=self._toggle_mic_row)
        self.mic_check.pack(anchor="w")
        mrow = tk.Frame(self.mic_f, bg=BG)
        mrow.pack(fill="x", pady=(2, 0))
        self.mic_label = tk.Label(mrow, text=self._h("Microfono:", "Microphone:", "Microfone:"), bg=BG, fg=TEXT_DIM, font=FONT)
        self.mic_label.pack(side="left")
        self.mic_device_var = tk.StringVar(value=self.config.get("mic_device", ""))
        self.mic_combo = ttk.Combobox(mrow, textvariable=self.mic_device_var, values=[],
                                       width=20, state="disabled", font=FONT)
        self.mic_combo.pack(side="left", padx=6)
        self.mic_refresh_btn = self._btn(mrow, "🔄", self._refresh_mic_devices, YELLOW)
        self.mic_refresh_btn.pack(side="left")

        self._toggle_record()
        self.chk_record.trace_add("write", self._on_setting_change)
        self.chk_mic.trace_add("write", self._on_setting_change)

        # ── Joystick / Gamepad
        sg = self._sec(parent, "Joystick / Gamepad",
            self._h(
            "Hay DOS formas distintas de usar un joystick, para dos "
            "situaciones distintas:\n\n"
            "1) Checkbox 'Usar joystick conectado a la PC': el control va "
            "enchufado (o por bluetooth) a la PC, y MirrorDeck lo "
            "reenvia al celular como si fuera un control fisico real. "
            "Solo funciona en juegos que YA soportan control fisico.\n\n"
            "2) Boton 'Instalar Tap Mapper': instala una segunda app en "
            "el celular que convierte botones del joystick en toques de "
            "pantalla. Ahi el joystick se empareja DIRECTO con el "
            "celular (bluetooth), no con la PC. Sirve para juegos que "
            "solo aceptan toques, no controles.\n\n"
            "Usa la opcion 1 primero (mas simple); si el juego no la "
            "reconoce, probá con Tap Mapper.",

            "There are TWO different ways to use a joystick, for two "
            "different situations:\n\n"
            "1) 'Use joystick connected to the PC' checkbox: the "
            "controller is plugged in (or paired via bluetooth) to the "
            "PC, and MirrorDeck forwards it to the phone as if it "
            "were a real physical controller. Only works in games that "
            "ALREADY support physical controllers.\n\n"
            "2) 'Install Tap Mapper' button: installs a second app on "
            "the phone that converts joystick buttons into screen "
            "taps. There, the joystick pairs DIRECTLY with the phone "
            "(bluetooth), not the PC. Useful for games that only accept "
            "taps, not controllers.\n\n"
            "Try option 1 first (simpler); if the game doesn't "
            "recognize it, try Tap Mapper.",

            "Existem DUAS formas diferentes de usar um joystick, para "
            "duas situacoes distintas:\n\n"
            "1) Caixa 'Usar joystick conectado ao PC': o controle fica "
            "conectado (ou pareado via bluetooth) ao PC, e o MirrorDeck "
            "o retransmite ao celular como se fosse um controle fisico "
            "de verdade. So funciona em jogos que JA suportam controle "
            "fisico.\n\n"
            "2) Botao 'Instalar Tap Mapper': instala um segundo app no "
            "celular que converte os botoes do joystick em toques na "
            "tela. Nesse caso o joystick pareia DIRETO com o celular "
            "(bluetooth), nao com o PC. Serve para jogos que so aceitam "
            "toques, nao controles.\n\n"
            "Use a opcao 1 primeiro (mais simples); se o jogo nao "
            "reconhecer, tente o Tap Mapper."))
        sg.pack(fill="x", pady=(0, 8))
        self.chk_gamepad = tk.BooleanVar(value=self.config.get("gamepad_enabled", False))
        tk.Checkbutton(sg, text=self._h(
                       "Usar joystick/control conectado a la PC",
                       "Use joystick/controller connected to the PC",
                       "Usar joystick/controle conectado ao PC"),
                       variable=self.chk_gamepad, bg=BG, fg=TEXT,
                       selectcolor=BG3, activebackground=BG, font=FONT).pack(
            padx=8, pady=4, anchor="w")
        tk.Label(sg,
                  text=self._h(
                       "Compatible con Xbox, PlayStation, Redragon y la mayoria\n"
                       "de controles genericos reconocidos por Windows.\n"
                       "Funciona por WiFi, no necesita cable.",
                       "Compatible with Xbox, PlayStation, Redragon and most\n"
                       "generic controllers recognized by Windows.\n"
                       "Works over WiFi, no cable needed.",
                       "Compativel com Xbox, PlayStation, Redragon e a maioria\n"
                       "dos controles genericos reconhecidos pelo Windows.\n"
                       "Funciona por WiFi, sem necessidade de cabo."),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8), justify="left").pack(
            padx=8, pady=(0, 6), anchor="w")

        tk.Frame(sg, bg=BG3, height=1).pack(fill="x", padx=8, pady=(2, 6))
        self.tapmapper_btn = self._btn(
            sg, self._h("📲 Instalar Tap Mapper en el celular", "📲 Install Tap Mapper on the phone", "📲 Instalar Tap Mapper no celular"),
            self._install_tap_mapper, BLUE)
        self.tapmapper_btn.pack(padx=8, pady=(0, 4), anchor="w")
        tk.Label(sg,
                  text=self._h(
                       "Tap Mapper es otra app (aparte) que convierte los botones\n"
                       "del joystick en toques de pantalla — para juegos que NO\n"
                       "soportan control fisico. El joystick se empareja con el\n"
                       "CELULAR (no con la PC). Necesita el celular ya conectado.",
                       "Tap Mapper is a separate app that converts joystick\n"
                       "buttons into screen taps — for games that do NOT\n"
                       "support physical controllers. The joystick pairs with\n"
                       "the PHONE (not the PC). Needs the phone already connected.",
                       "Tap Mapper e outro app (separado) que converte os botoes\n"
                       "do joystick em toques na tela — para jogos que NAO\n"
                       "suportam controle fisico. O joystick pareia com o\n"
                       "CELULAR (nao com o PC). Precisa do celular ja conectado."),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8), justify="left").pack(
            padx=8, pady=(0, 6), anchor="w")

        # Nota: los botones de Iniciar/Detener Mirror, "Como capturar en
        # OBS" e "Instructivo completo" ahora viven en una barra fija
        # arriba de todo (ver _build_ui), para que siempre esten a la
        # vista sin importar cuanto crezca esta columna.

    # ── BUSQUEDA AUTOMATICA (mDNS) ──────────────────────────────
    # Android anuncia la IP y el puerto (de vinculacion y de conexion)
    # en la red local vía mDNS, el mismo mecanismo que usan Chromecasts
    # e impresoras de red para "avisar" que estan ahi. adb ya sabe
    # escuchar eso (`adb mdns services`) — usamos ese dato para evitar
    # que el usuario tenga que leerlo e ingresarlo a mano. Esto NO
    # saltea ninguna autenticacion: solo autocompleta IP/puerto, que
    # ya eran datos visibles en la red; el codigo de 6 digitos (y el
    # emparejamiento en si) lo sigue autorizando el dueño del celular.
    def _search_pair_device(self):
        self._run_mdns_search("pairing", self.search_pair_btn, self._fill_pair_fields)

    def _search_connect_device(self):
        self._run_mdns_search("connect", self.search_connect_btn, self._fill_connect_fields)

    def _run_mdns_search(self, kind, btn, fill_cb):
        btn.config(state="disabled", text=self._h("Buscando...", "Searching...", "Buscando..."))
        def bg():
            devices = mdns_discover(kind)
            def done():
                btn.config(state="normal", text=self._h("🔍 Buscar", "🔍 Search", "🔍 Buscar"))
                if not devices:
                    messagebox.showinfo(
                        self._h("Sin resultados", "No results", "Sem resultados"),
                        self._h(
                            "No se encontro ningun celular en la red.\n\n"
                            "Verifica que el celular y la PC esten en la misma red WiFi, "
                            "y que 'Depuracion inalambrica' este activada (y la pantalla "
                            "de vinculacion abierta, si estas emparejando por primera vez).\n\n"
                            "Tambien podes cargar la IP y el puerto a mano.",
                            "No phone was found on the network.\n\n"
                            "Make sure the phone and PC are on the same WiFi network, "
                            "and that 'Wireless debugging' is on (and the pairing screen "
                            "open, if you're pairing for the first time).\n\n"
                            "You can also enter the IP and port manually.",
                            "Nenhum celular foi encontrado na rede.\n\n"
                            "Verifique se o celular e o PC estao na mesma rede WiFi, "
                            "e se a 'Depuracao sem fio' esta ativada (e a tela de "
                            "pareamento aberta, se estiver pareando pela primeira vez).\n\n"
                            "Voce tambem pode digitar o IP e a porta manualmente."))
                    return
                if len(devices) == 1:
                    fill_cb(devices[0])
                else:
                    self._pick_mdns_device(devices, fill_cb)
            self.root.after(0, done)
        threading.Thread(target=bg, daemon=True).start()

    def _pick_mdns_device(self, devices, fill_cb):
        """Si mDNS encuentra mas de un celular en la red (ej. wifi
        familiar/oficina compartida), SIEMPRE mostramos este selector en
        vez de auto-elegir el primero — para no arriesgarnos a emparejar
        o conectar por error con el celular de otra persona."""
        win = tk.Toplevel(self.root)
        win.title(self._h("Elegi el dispositivo", "Choose the device", "Escolha o dispositivo"))
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        tk.Label(win, text=self._h(
                     "Se encontro mas de un celular en la red.\nElegi cual es el tuyo:",
                     "More than one phone was found on the network.\nPick which one is yours:",
                     "Mais de um celular foi encontrado na rede.\nEscolha qual e o seu:"),
                 bg=BG, fg=TEXT, font=FONT, justify="left").pack(padx=20, pady=(16, 8))
        for d in devices:
            b = tk.Button(win, text=f"📱  {d['ip']}:{d['port']}",
                           font=FONT, bg=BG3, fg=TEXT, activebackground=BG4,
                           relief="flat", padx=12, pady=6,
                           command=lambda dd=d: (fill_cb(dd), win.destroy()))
            b.pack(padx=20, pady=4, fill="x")
        tk.Button(win, text=self._h("Cancelar", "Cancel", "Cancelar"),
                  command=win.destroy, bg=BG, fg=TEXT_DIM, relief="flat").pack(pady=(4, 16))

    def _fill_pair_fields(self, d):
        self.pair_ip_var.set(d["ip"])
        self.pair_port_var.set(d["port"])
        self.pair_lbl.config(
            text=self._h(f"✓ Detectado: {d['ip']}:{d['port']}. Ahora solo falta el codigo de 6 digitos.",
                          f"✓ Detected: {d['ip']}:{d['port']}. Now you just need the 6-digit code.",
                          f"✓ Detectado: {d['ip']}:{d['port']}. Agora so falta o codigo de 6 digitos."),
            fg=GREEN)

    def _fill_connect_fields(self, d):
        self.ip_var.set(d["ip"])
        self.port_var.set(d["port"])
        self._log(self._h(f"🔍 Detectado automaticamente: {d['ip']}:{d['port']}",
                           f"🔍 Auto-detected: {d['ip']}:{d['port']}",
                           f"🔍 Detectado automaticamente: {d['ip']}:{d['port']}"))

    # ── EMPAREJAMIENTO ───────────────────────────────────────────
    def _do_pair(self):
        if self.pairing:
            return
        ip   = self.pair_ip_var.get().strip()
        port = self.pair_port_var.get().strip()
        code = self.pair_code_var.get().strip()
        if not ip or not IP_RE.match(ip):
            self.pair_lbl.config(text=self._h("IP invalida. Ejemplo: 192.168.1.105",
                                               "Invalid IP. Example: 192.168.1.105",
                                               "IP invalido. Exemplo: 192.168.1.105"), fg=RED)
            return
        if not port or not PORT_RE.match(port):
            self.pair_lbl.config(text=self._h("Puerto invalido.", "Invalid port.", "Porta invalida."), fg=RED)
            return
        if not code or len(code) < 6:
            self.pair_lbl.config(text=self._h("Codigo invalido. Debe tener 6 digitos.",
                                               "Invalid code. Must have 6 digits.",
                                               "Codigo invalido. Deve ter 6 digitos."), fg=RED)
            return
        self.pairing = True
        self.pair_btn.config(state="disabled", text=self._h("Emparejando...", "Pairing...", "Pareando..."), fg=TEXT_DIM)
        self.pair_lbl.config(text=self._h("Emparejando con el celular...", "Pairing with the phone...", "Pareando com o celular..."), fg=YELLOW)
        threading.Thread(target=self._pair_bg, args=(ip, port, code), daemon=True).start()

    def _pair_bg(self, ip, port, code):
        rc, out, err = run_adb(["pair", f"{ip}:{port}", code], timeout=30)
        ok = rc == 0 and "successfully" in out.lower()
        def done():
            self.pairing = False
            self.pair_btn.config(state="normal", text=self._h("Emparejar", "Pair", "Parear"), fg=ORANGE)
            if ok:
                self.pair_lbl.config(
                    text=self._h(
                         "✓ Emparejado correctamente.\n"
                         "Ahora conecta con la IP y el PUERTO DE DEPURACION (no el de vinculacion).",
                         "✓ Paired successfully.\n"
                         "Now connect with the IP and the DEBUGGING PORT (not the pairing one).",
                         "✓ Pareado com sucesso.\n"
                         "Agora conecte com o IP e a PORTA DE DEPURACAO (nao a de pareamento)."),
                    fg=GREEN)
                self._log(self._h(f"✓ Emparejado: {out}", f"✓ Paired: {out}", f"✓ Pareado: {out}"))
                self.ip_var.set(ip)
            else:
                msg = out or err or self._h("Sin respuesta", "No response", "Sem resposta")
                self.pair_lbl.config(
                    text=self._h(
                         f"✗ Error: {msg}\n"
                         "Verificá que el codigo no haya expirado.",
                         f"✗ Error: {msg}\n"
                         "Check that the code hasn't expired.",
                         f"✗ Erro: {msg}\n"
                         "Verifique se o codigo nao expirou."),
                    fg=RED)
                self._log(self._h(f"✗ Error al emparejar: {msg}", f"✗ Error pairing: {msg}", f"✗ Erro ao parear: {msg}"))
        self.root.after(0, done)

    # ── CONEXION ─────────────────────────────────────────────────
    def _on_ip_change(self, *_):
        if not self.auto_var.get():
            return
        ip = self.ip_var.get().strip()
        if not IP_RE.match(ip):
            return
        if self.auto_job:
            self.root.after_cancel(self.auto_job)
        self.auto_job = self.root.after(800, lambda: self._trigger_auto(ip))

    def _trigger_auto(self, ip):
        self.auto_job = None
        if self.connecting or self.ip_var.get().strip() != ip:
            return
        self._connect_wifi(ip, self.port_var.get().strip() or "5555")

    def _connect_manual(self):
        ip   = self.ip_var.get().strip()
        port = self.port_var.get().strip() or "5555"
        if not ip:
            messagebox.showwarning(self._h("IP requerida", "IP required", "IP obrigatorio"),
                                    self._h("Ingresá la IP del celular", "Enter the phone's IP", "Digite o IP do celular"))
            return
        if not IP_RE.match(ip):
            messagebox.showerror(self._h("IP invalida", "Invalid IP", "IP invalido"),
                                  self._h(f"'{ip}' no es valida.\nEjemplo: 192.168.1.105",
                                          f"'{ip}' is not valid.\nExample: 192.168.1.105",
                                          f"'{ip}' nao e valido.\nExemplo: 192.168.1.105"))
            return
        self._connect_wifi(ip, port)

    def _connect_wifi(self, ip, port):
        if self.connecting:
            return
        self.connecting = True
        self.connect_btn.config(state="disabled")
        self.config["last_ip"]   = ip
        self.config["last_port"] = port
        self._save_config()
        self._set_status(self._h(f"Conectando a {ip}:{port}...", f"Connecting to {ip}:{port}...", f"Conectando a {ip}:{port}..."), YELLOW)
        self._conn_ind("connecting")
        threading.Thread(target=self._connect_bg,
                          args=(ip, port, False), daemon=True).start()

    def _connect_bg(self, ip, port, silent):
        # Limpiar TLS antes de conectar
        tls = get_tls_entries()
        for serial in tls:
            run_adb(["disconnect", serial])
            if tls:
                self._log(self._h(f"→ Entrada TLS eliminada: {serial[:35]}...",
                                   f"→ TLS entry removed: {serial[:35]}...",
                                   f"→ Entrada TLS removida: {serial[:35]}..."))

        time.sleep(0.4)
        rc, out, err = run_adb(["connect", f"{ip}:{port}"], timeout=15)
        ok = rc == 0 and ("connected" in out.lower() or "already" in out.lower())

        def done():
            self.connecting = False
            self.connect_btn.config(state="normal")
            if ok:
                self._log(f"✓ {out}")
                self._conn_ind("connected", ip, port)
                self._set_status(self._h(f"Conectado a {ip}:{port}", f"Connected to {ip}:{port}", f"Conectado a {ip}:{port}"), GREEN)
                self.refresh_devices()
            else:
                msg = out or err or self._h("Sin respuesta", "No response", "Sem resposta")
                self._log(f"✗ {msg}")
                self._conn_ind("disconnected")
                self._set_status(self._h("Sin conexion", "No connection", "Sem conexao"), TEXT_DIM)
                if not silent:
                    if "protocol fault" in msg.lower() or "couldn't read status" in msg.lower():
                        if messagebox.askyesno(
                            self._h("Problema con ADB", "ADB issue", "Problema com o ADB"),
                            self._h(
                                "Se detectó un problema con ADB.\n"
                                "Esto pasa después de reiniciar la PC.\n\n"
                                "¿Querés que reinicie ADB automáticamente ahora?",
                                "An ADB issue was detected.\n"
                                "This happens after restarting the PC.\n\n"
                                "Do you want to restart ADB automatically now?",
                                "Foi detectado um problema com o ADB.\n"
                                "Isso acontece depois de reiniciar o PC.\n\n"
                                "Quer que eu reinicie o ADB automaticamente agora?")
                        ):
                            self.root.after(100, self._restart_adb)
                    else:
                        messagebox.showerror(
                            self._h("Error de conexion", "Connection error", "Erro de conexao"),
                            self._h(
                                f"No se pudo conectar a {ip}:{port}\n\n{msg}\n\n"
                                "Primera vez conectando:\n"
                                "→ Primero usa la seccion 'Emparejar'\n"
                                "→ El puerto de conexion es DIFERENTE al de vinculacion\n\n"
                                "• ¿Celu y PC en la misma red WiFi?\n"
                                "• ¿Puerto correcto? (el de Depuracion inalambrica)",
                                f"Could not connect to {ip}:{port}\n\n{msg}\n\n"
                                "Connecting for the first time:\n"
                                "→ Use the 'Pair' section first\n"
                                "→ The connection port is DIFFERENT from the pairing one\n\n"
                                "• Phone and PC on the same WiFi network?\n"
                                "• Correct port? (the one from Wireless debugging)",
                                f"Nao foi possivel conectar a {ip}:{port}\n\n{msg}\n\n"
                                "Conectando pela primeira vez:\n"
                                "→ Use primeiro a secao 'Parear'\n"
                                "→ A porta de conexao e DIFERENTE da porta de pareamento\n\n"
                                "• Celular e PC na mesma rede WiFi?\n"
                                "• Porta correta? (a da Depuracao sem fio)")
                        )
        self.root.after(0, done)

    def _conn_ind(self, state, ip="", port=""):
        d = {
            "connected":    (self._h(f"● Conectado ({ip}:{port})", f"● Connected ({ip}:{port})", f"● Conectado ({ip}:{port})"), GREEN),
            "connecting":   (self._h("◌ Conectando...", "◌ Connecting...", "◌ Conectando..."), YELLOW),
            "disconnected": (self._h("● Sin conexion", "● No connection", "● Sem conexao"), TEXT_DIM),
        }
        txt, color = d.get(state, (self._h("● Sin conexion", "● No connection", "● Sem conexao"), TEXT_DIM))
        self.conn_lbl.config(text=txt, fg=color)

    def _disconnect(self):
        ip   = self.ip_var.get().strip()
        port = self.port_var.get().strip() or "5555"
        def do():
            tls = get_tls_entries()
            for serial in tls:
                run_adb(["disconnect", serial])
            if ip:
                run_adb(["disconnect", f"{ip}:{port}"])
            else:
                run_adb(["disconnect"])
            self.root.after(500, self.refresh_devices)
        threading.Thread(target=do, daemon=True).start()
        self._conn_ind("disconnected")
        self._set_status(self._h("Desconectado", "Disconnected", "Desconectado"), TEXT_DIM)
        self._log(self._h("→ Desconectado", "→ Disconnected", "→ Desconectado"))

    def _forget_device(self):
        """Desconecta y borra de ESTA PC la IP/puerto/datos de emparejamiento
        del celular actual — pensado para cuando usaste la app de visita en
        otra casa/oficina y no queres dejar rastro para quien la use despues
        en esa misma PC. NO puede (ni deberia poder) revocar el permiso del
        lado del celular — eso lo controla unicamente el dueño del celular,
        desde el celular mismo."""
        if not messagebox.askyesno(
                self._h("Olvidar este dispositivo", "Forget this device", "Esquecer este dispositivo"),
                self._h(
                    "Esto desconecta el celular actual y borra la IP, el puerto "
                    "y los datos de emparejamiento guardados en ESTA PC — util "
                    "si estabas de visita en otra casa u oficina y no queres "
                    "dejar rastro para quien use esta PC despues.\n\n"
                    "IMPORTANTE: esto NO revoca el permiso del lado del celular. "
                    "Para eso hay que ir al celular: Depuracion inalambrica → "
                    "'Dispositivos emparejados' → quitar esta PC de la lista.\n\n"
                    "¿Continuar?",
                    "This disconnects the current phone and clears the IP, "
                    "port and pairing data saved on THIS PC — useful if you "
                    "were visiting another home or office and don't want to "
                    "leave a trace for whoever uses this PC afterward.\n\n"
                    "IMPORTANT: this does NOT revoke the phone's side of the "
                    "permission. For that, go to the phone: Wireless "
                    "debugging → 'Paired devices' → remove this PC from the "
                    "list.\n\n"
                    "Continue?",
                    "Isso desconecta o celular atual e apaga o IP, a porta e "
                    "os dados de pareamento salvos NESTE PC — util se voce "
                    "estava visitando outra casa ou escritorio e nao quer "
                    "deixar rastro para quem usar este PC depois.\n\n"
                    "IMPORTANTE: isso NAO revoga a permissao do lado do "
                    "celular. Para isso, va no celular: Depuracao sem fio → "
                    "'Dispositivos pareados' → remova este PC da lista.\n\n"
                    "Continuar?")):
            return

        def do():
            tls = get_tls_entries()
            for serial in tls:
                run_adb(["disconnect", serial])
            run_adb(["disconnect"])
        threading.Thread(target=do, daemon=True).start()

        self.ip_var.set("")
        self.port_var.set("")
        self.pair_ip_var.set("")
        self.pair_port_var.set("")
        self.pair_code_var.set("")
        self.config["last_ip"] = ""
        self.config["last_port"] = "5555"
        self._save_config()

        self._conn_ind("disconnected")
        self._set_status(self._h("Dispositivo olvidado", "Device forgotten", "Dispositivo esquecido"), TEXT_DIM)
        self._log(self._h("→ Dispositivo olvidado: IP, puerto y datos de emparejamiento borrados de esta PC.",
                           "→ Device forgotten: IP, port and pairing data cleared from this PC.",
                           "→ Dispositivo esquecido: IP, porta e dados de pareamento apagados deste PC."))

    def _restart_adb(self):
        """Reinicia ADB limpiando entradas TLS y reconectando automaticamente."""
        self._set_status(self._h("Reiniciando ADB...", "Restarting ADB...", "Reiniciando ADB..."), YELLOW)
        self._log(self._h("→ Reiniciando ADB...", "→ Restarting ADB...", "→ Reiniciando ADB..."))
        def do():
            # 1. Limpiar TLS
            tls = get_tls_entries()
            for serial in tls:
                run_adb(["disconnect", serial])
                self._log(self._h(f"→ TLS eliminado: {serial[:35]}...", f"→ TLS removed: {serial[:35]}...", f"→ TLS removido: {serial[:35]}..."))
            # 2. Kill + start
            run_adb(["kill-server"], timeout=8)
            time.sleep(1.2)
            run_adb(["start-server"], timeout=10)
            time.sleep(0.5)
            # 3. Limpiar TLS que volvieron a aparecer
            tls2 = get_tls_entries()
            for serial in tls2:
                run_adb(["disconnect", serial])
            # 4. Reconectar
            last_ip   = self.config.get("last_ip", "")
            last_port = self.config.get("last_port", "5555")
            def done():
                self._log(self._h("✓ ADB reiniciado y limpio.", "✓ ADB restarted and cleaned up.", "✓ ADB reiniciado e limpo."))
                self._set_status(self._h("ADB reiniciado", "ADB restarted", "ADB reiniciado"), GREEN)
                if last_ip and IP_RE.match(last_ip):
                    self._log(self._h(f"→ Reconectando a {last_ip}:{last_port}...",
                                       f"→ Reconnecting to {last_ip}:{last_port}...",
                                       f"→ Reconectando a {last_ip}:{last_port}..."))
                    threading.Thread(
                        target=self._connect_bg,
                        args=(last_ip, last_port, True),
                        daemon=True
                    ).start()
                else:
                    self.root.after(500, self.refresh_devices)
            self.root.after(0, done)
        threading.Thread(target=do, daemon=True).start()

    # ── DISPOSITIVOS ─────────────────────────────────────────────
    def refresh_devices(self):
        threading.Thread(target=self._refresh_bg, daemon=True).start()

    def _refresh_bg(self):
        # Limpiar TLS antes de listar
        tls = get_tls_entries()
        for serial in tls:
            run_adb(["disconnect", serial])

        _, out, _ = run_adb(["devices", "-l"])
        devices = []
        for line in (out or "").split("\n")[1:]:
            line = line.strip()
            if not line or "offline" in line:
                continue
            # Ignorar entradas TLS
            if "_adb-tls" in line or "adb-tls-connect" in line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                info = {"serial": parts[0], "model": ""}
                for p in parts[2:]:
                    if p.startswith("model:"):
                        info["model"] = p.split(":", 1)[1]
                devices.append(info)
        self.devices = devices
        self.root.after(0, self._update_device_list)

    def _update_device_list(self):
        self.device_list.delete(0, "end")
        if not self.devices:
            self.device_list.insert("end", self._h("  Sin dispositivos detectados", "  No devices detected", "  Nenhum dispositivo detectado"))
            self._set_status(self._h("Sin dispositivos", "No devices", "Sem dispositivos"), TEXT_DIM)
            return
        for d in self.devices:
            lbl = f"  {d['serial']}"
            if d["model"]:
                lbl += f"  [{d['model']}]"
            self.device_list.insert("end", lbl)
        self.device_list.selection_set(0)
        self._on_device_select(None)
        self._set_status(self._h(f"{len(self.devices)} dispositivo(s) listo(s)",
                                  f"{len(self.devices)} device(s) ready",
                                  f"{len(self.devices)} dispositivo(s) pronto(s)"), GREEN)
        self._log(self._h(f"✓ {len(self.devices)} dispositivo(s)", f"✓ {len(self.devices)} device(s)", f"✓ {len(self.devices)} dispositivo(s)"))

    def _on_device_select(self, _):
        sel = self.device_list.curselection()
        if sel and self.devices and sel[0] < len(self.devices):
            d = self.devices[sel[0]]
            self.selected_serial.set(d["serial"])
            self.selected_lbl.config(
                text=self._h(f"Seleccionado: {d['serial']}  {d['model']}",
                             f"Selected: {d['serial']}  {d['model']}",
                             f"Selecionado: {d['serial']}  {d['model']}"), fg=GREEN)

    def _open_record_dir(self):
        d = Path(self.record_dir_var.get().strip()
                  or (Path.home() / "Videos" / "MirrorDeck"))
        try:
            d.mkdir(parents=True, exist_ok=True)
            os.startfile(str(d))
        except Exception as e:
            messagebox.showerror("Error", self._h(f"No se pudo abrir la carpeta:\n{e}",
                                                    f"Could not open the folder:\n{e}",
                                                    f"Nao foi possivel abrir a pasta:\n{e}"))

    def _device_info(self):
        """Muestra la resolucion real y densidad que reporta el celular
        (adb shell wm size / wm density), para poder comparar contra los
        valores de --max-size elegidos en Video y entender si tienen
        efecto visible o no (--max-size solo puede achicar, nunca agranda
        mas alla de la resolucion nativa)."""
        if not self.devices:
            messagebox.showwarning(self._h("Sin dispositivo", "No device", "Sem dispositivo"),
                                   self._h("Primero conecta el celular por WiFi.",
                                           "First connect the phone via WiFi.",
                                           "Primeiro conecte o celular por WiFi."))
            return
        self._log(self._h("→ Consultando info del celular...", "→ Querying phone info...", "→ Consultando info do celular..."))
        threading.Thread(target=self._device_info_bg, daemon=True).start()

    def _device_info_bg(self):
        _, size_out, _ = run_adb(["shell", "wm", "size"])
        _, density_out, _ = run_adb(["shell", "wm", "density"])
        _, model_out, _ = run_adb(["shell", "getprop", "ro.product.model"])
        _, android_out, _ = run_adb(["shell", "getprop", "ro.build.version.release"])

        # --max-size limita el LADO MAS LARGO de la pantalla, no el ancho.
        # Un telefono en vertical suele reportar algo como "1080x2408": el
        # lado largo real es 2408, no 1080 — asi que poner Resolucion en
        # 1080 recorta MUCHO mas de lo que parece. Con esto calculamos una
        # recomendacion concreta en vez de dejar al usuario adivinar.
        advice = ""
        m = re.search(r"(\d+)\s*x\s*(\d+)", size_out or "")
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            long_side = max(w, h)
            current = self.res_var.get()
            cur_num = int(current) if current.isdigit() and current != "0" else None
            if cur_num and cur_num < long_side:
                advice = self._h(
                    f"\nEl lado mas largo real de tu pantalla es {long_side}px. "
                    f"Con Resolucion en {cur_num}, scrcpy achica ese lado a "
                    f"{cur_num}px — bastante menos que lo real. Subila (probá "
                    f"1920) o poné 0 (original) para notar mas nitidez.",
                    f"\nThe real long side of your screen is {long_side}px. "
                    f"With Resolution at {cur_num}, scrcpy shrinks that side to "
                    f"{cur_num}px — quite a bit less than the real one. Raise it "
                    f"(try 1920) or set it to 0 (original) for more sharpness.",
                    f"\nO lado mais longo real da sua tela e {long_side}px. "
                    f"Com Resolucao em {cur_num}, o scrcpy diminui esse lado "
                    f"para {cur_num}px — bem menos que o real. Aumente (tente "
                    f"1920) ou coloque 0 (original) para notar mais nitidez."
                )
            elif cur_num and cur_num >= long_side:
                advice = self._h(
                    f"\nEl lado mas largo real de tu pantalla es {long_side}px, "
                    f"igual o menor a tu Resolucion actual ({cur_num}) — por eso "
                    f"no vas a notar diferencia subiendola mas.",
                    f"\nThe real long side of your screen is {long_side}px, "
                    f"equal to or less than your current Resolution ({cur_num}) — "
                    f"that's why raising it further won't make a visible difference.",
                    f"\nO lado mais longo real da sua tela e {long_side}px, "
                    f"igual ou menor que sua Resolucao atual ({cur_num}) — por "
                    f"isso voce nao vai notar diferenca aumentando mais."
                )

        msg = (
            f"{self._h('Modelo', 'Model', 'Modelo')}: {model_out or '?'}\n"
            f"Android: {android_out or '?'}\n"
            f"{size_out or self._h('Sin datos de resolucion', 'No resolution data', 'Sem dados de resolucao')}\n"
            f"{density_out or ''}"
            f"{advice}"
        ).strip()

        def done():
            self._log(f"ℹ {msg.replace(chr(10), '  |  ')}")
            messagebox.showinfo(self._h("Info del celular", "Phone info", "Info do celular"), msg)
        self.root.after(0, done)

    # ── PERFILES ─────────────────────────────────────────────────
    def _profile_snapshot(self):
        return {
            "max_fps":         self.fps_var.get(),
            "bitrate":         self.bitrate_var.get(),
            "resolution":      self.res_var.get(),
            "video_codec":     self.vcodec_var.get(),
            "video_buffer":    self.vbuf_var.get(),
            "audio_enabled":   self.chk_audio.get(),
            "audio_codec":     self.codec_var.get(),
            "audio_buffer":    self.abuf_var.get(),
            "show_touches":    self.chk_touches.get(),
            "stay_awake":      self.chk_awake.get(),
            "borderless":      self.chk_borderless.get(),
            "always_on_top":   self.chk_ontop.get(),
            "window_title":    self.title_var.get(),
            "gamepad_enabled": self.chk_gamepad.get(),
            "record_enabled":  self.chk_record.get(),
            "mic_enabled":     self.chk_mic.get(),
        }

    def _apply_profile_settings(self, settings):
        str_vars = {
            "max_fps": self.fps_var, "bitrate": self.bitrate_var,
            "resolution": self.res_var, "video_codec": self.vcodec_var,
            "video_buffer": self.vbuf_var, "audio_codec": self.codec_var,
            "audio_buffer": self.abuf_var, "window_title": self.title_var,
        }
        bool_vars = {
            "audio_enabled": self.chk_audio, "show_touches": self.chk_touches,
            "stay_awake": self.chk_awake, "borderless": self.chk_borderless,
            "always_on_top": self.chk_ontop, "gamepad_enabled": self.chk_gamepad,
            "record_enabled": self.chk_record, "mic_enabled": self.chk_mic,
        }
        for key, var in str_vars.items():
            if key in settings:
                var.set(settings[key])
        for key, var in bool_vars.items():
            if key in settings:
                var.set(bool(settings[key]))
        self._toggle_audio()
        self._toggle_record()

    def _load_profile(self, name):
        settings = self.config.get("profiles", {}).get(name)
        if not settings:
            return
        self._apply_profile_settings(settings)
        self._log(self._h(f"→ Perfil '{name}' aplicado.", f"→ Profile '{name}' applied.", f"→ Perfil '{name}' aplicado."))

    def _save_profile(self):
        profiles = self.config.get("profiles", {})
        current = self.profile_var.get().strip()
        name = simpledialog.askstring(
            self._h("Guardar perfil", "Save profile", "Salvar perfil"), self._h("Nombre del perfil:", "Profile name:", "Nome do perfil:"),
            initialvalue=current, parent=self.root)
        if not name:
            return
        name = name.strip()[:20]
        if not name:
            return
        if name not in profiles and len(profiles) >= 4:
            messagebox.showwarning(
                self._h("Maximo 4 perfiles", "Maximum 4 profiles", "Maximo de 4 perfis"),
                self._h(
                    "Ya tenes 4 perfiles guardados. Borra uno o sobreescribi "
                    "uno existente eligiendolo de la lista antes de guardar.",
                    "You already have 4 saved profiles. Delete one or overwrite "
                    "an existing one by picking it from the list before saving.",
                    "Voce ja tem 4 perfis salvos. Exclua um ou sobrescreva um "
                    "existente escolhendo-o na lista antes de salvar."))
            return
        profiles[name] = self._profile_snapshot()
        self.config["profiles"] = profiles
        self._save_config()
        self.profile_combo["values"] = list(profiles.keys())
        self.profile_var.set(name)
        self._log(self._h(f"✓ Perfil '{name}' guardado.", f"✓ Profile '{name}' saved.", f"✓ Perfil '{name}' salvo."))

    def _delete_profile(self):
        name = self.profile_var.get().strip()
        profiles = self.config.get("profiles", {})
        if not name or name not in profiles:
            messagebox.showinfo(self._h("Sin perfil", "No profile", "Sem perfil"),
                                 self._h("Elegi un perfil de la lista primero.",
                                         "Pick a profile from the list first.",
                                         "Escolha um perfil da lista primeiro."))
            return
        if not messagebox.askyesno(self._h("Borrar perfil", "Delete profile", "Excluir perfil"),
                                    self._h(f"¿Borrar el perfil '{name}'?", f"Delete profile '{name}'?", f"Excluir o perfil '{name}'?")):
            return
        del profiles[name]
        self.config["profiles"] = profiles
        self._save_config()
        self.profile_combo["values"] = list(profiles.keys())
        self.profile_var.set("")
        self._log(self._h(f"→ Perfil '{name}' borrado.", f"→ Profile '{name}' deleted.", f"→ Perfil '{name}' excluido."))

    # ── AUDIO ────────────────────────────────────────────────────
    def _toggle_audio(self):
        state = "normal" if self.chk_audio.get() else "disabled"
        for w in self.audio_f.winfo_children():
            try:
                w.config(state=state)
            except Exception:
                pass

    # ── GRABACION / MICROFONO ───────────────────────────────────
    def _toggle_record(self):
        self.mic_check.config(state="normal" if self.chk_record.get() else "disabled")
        self._toggle_mic_row()

    def _toggle_mic_row(self):
        active = self.chk_record.get() and self.chk_mic.get()
        self.mic_label.config(state="normal" if active else "disabled")
        self.mic_combo.config(state="readonly" if active else "disabled")
        self.mic_refresh_btn.config(state="normal" if active else "disabled")

    def _refresh_mic_devices(self):
        self._log(self._h("→ Buscando microfonos disponibles...", "→ Looking for available microphones...", "→ Procurando microfones disponiveis..."))
        threading.Thread(target=self._refresh_mic_devices_bg, daemon=True).start()

    def _refresh_mic_devices_bg(self):
        try:
            ffmpeg = ensure_ffmpeg(log_cb=self._log)
            devices = list_mic_devices(ffmpeg)
        except Exception as e:
            self._log(self._h(f"✗ No se pudo listar microfonos: {e}", f"✗ Could not list microphones: {e}", f"✗ Nao foi possivel listar microfones: {e}"))
            return

        def done():
            self.mic_combo["values"] = devices
            if devices and self.mic_device_var.get() not in devices:
                self.mic_device_var.set(devices[0])
            if devices:
                self._log(self._h(f"✓ {len(devices)} microfono(s) encontrado(s).",
                                   f"✓ {len(devices)} microphone(s) found.",
                                   f"✓ {len(devices)} microfone(s) encontrado(s)."))
            else:
                self._log(self._h("⚠ No se encontro ningun microfono.", "⚠ No microphone found.", "⚠ Nenhum microfone encontrado."))
        self.root.after(0, done)

    # ── TAP MAPPER ───────────────────────────────────────────────
    def _install_tap_mapper(self):
        if not self.devices:
            messagebox.showwarning(self._h("Sin dispositivo", "No device", "Sem dispositivo"),
                                   self._h("Primero conecta el celular por WiFi.",
                                           "First connect the phone via WiFi.",
                                           "Primeiro conecte o celular por WiFi."))
            return
        apk = app_dir() / TAP_MAPPER_APK
        if not apk.exists():
            messagebox.showerror(
                self._h("Tap Mapper no encontrado", "Tap Mapper not found", "Tap Mapper nao encontrado"),
                self._h(
                    f"No se encontro '{TAP_MAPPER_APK}' junto al programa.\n\n"
                    "Hay que compilar el APK una vez con Android Studio (ver el "
                    f"README del proyecto tap-mapper) y copiar el resultado como "
                    f"'{TAP_MAPPER_APK}' en la carpeta de MirrorDeck.",
                    f"'{TAP_MAPPER_APK}' was not found next to the program.\n\n"
                    "The APK needs to be built once with Android Studio (see the "
                    f"README of the tap-mapper project) and the result copied as "
                    f"'{TAP_MAPPER_APK}' into the MirrorDeck folder.",
                    f"'{TAP_MAPPER_APK}' nao foi encontrado junto ao programa.\n\n"
                    "E preciso compilar o APK uma vez com o Android Studio (veja "
                    f"o README do projeto tap-mapper) e copiar o resultado como "
                    f"'{TAP_MAPPER_APK}' na pasta do MirrorDeck."))
            return
        self.tapmapper_btn.config(state="disabled", text=self._h("Instalando...", "Installing...", "Instalando..."))
        self._log(self._h("→ Instalando Tap Mapper en el celular...", "→ Installing Tap Mapper on the phone...", "→ Instalando o Tap Mapper no celular..."))
        threading.Thread(target=self._install_tap_mapper_bg,
                          args=(str(apk),), daemon=True).start()

    def _install_tap_mapper_bg(self, apk_path):
        rc, out, err = run_adb(["install", "-r", apk_path], timeout=60)
        ok = rc == 0 and "success" in (out or "").lower()

        auto_enabled = False
        if ok:
            auto_enabled = self._try_enable_tap_mapper_accessibility()
            # Abre la app en el celular para que la persona vea que quedo.
            run_adb(["shell", "am", "start", "-n",
                     f"{TAP_MAPPER_PKG}/.MainActivity"])

        def done():
            self.tapmapper_btn.config(state="normal",
                                       text=self._h("📲 Instalar Tap Mapper en el celular",
                                                     "📲 Install Tap Mapper on the phone",
                                                     "📲 Instalar Tap Mapper no celular"))
            if ok:
                self._log(self._h("✓ Tap Mapper instalado.", "✓ Tap Mapper installed.", "✓ Tap Mapper instalado."))
                if auto_enabled:
                    self._log(self._h("✓ Servicio de accesibilidad activado automaticamente.",
                                       "✓ Accessibility service enabled automatically.",
                                       "✓ Servico de acessibilidade ativado automaticamente."))
                    messagebox.showinfo(
                        self._h("Tap Mapper instalado", "Tap Mapper installed", "Tap Mapper instalado"),
                        self._h(
                            "Tap Mapper se instalo y el servicio de accesibilidad "
                            "se activo solo.\n\n"
                            "En el celular: empareja el joystick por Bluetooth, "
                            "abri Tap Mapper → 'Mapear botones del joystick' y "
                            "configura cada boton.",
                            "Tap Mapper was installed and the accessibility "
                            "service turned on by itself.\n\n"
                            "On the phone: pair the joystick over Bluetooth, "
                            "open Tap Mapper → 'Map joystick buttons' and "
                            "configure each button.",
                            "O Tap Mapper foi instalado e o servico de "
                            "acessibilidade se ativou sozinho.\n\n"
                            "No celular: pareie o joystick por Bluetooth, abra "
                            "o Tap Mapper → 'Mapear botoes do joystick' e "
                            "configure cada botao."))
                else:
                    self._log(self._h("⚠ No se pudo activar el servicio de accesibilidad automaticamente.",
                                       "⚠ Could not enable the accessibility service automatically.",
                                       "⚠ Nao foi possivel ativar o servico de acessibilidade automaticamente."))
                    messagebox.showinfo(
                        self._h("Tap Mapper instalado", "Tap Mapper installed", "Tap Mapper instalado"),
                        self._h(
                            "Tap Mapper se instalo, pero hay que activar el "
                            "servicio de accesibilidad a mano (una sola vez):\n\n"
                            "En el celular: Tap Mapper → 'Activar servicio de "
                            "Accesibilidad' → buscar 'Tap Mapper' en la lista → "
                            "activarlo.",
                            "Tap Mapper was installed, but the accessibility "
                            "service needs to be enabled by hand (one time only):\n\n"
                            "On the phone: Tap Mapper → 'Enable Accessibility "
                            "Service' → find 'Tap Mapper' in the list → "
                            "turn it on.",
                            "O Tap Mapper foi instalado, mas e preciso ativar o "
                            "servico de acessibilidade manualmente (uma unica "
                            "vez):\n\n"
                            "No celular: Tap Mapper → 'Ativar servico de "
                            "Acessibilidade' → procure 'Tap Mapper' na lista → "
                            "ative."))
            else:
                msg = out or err or self._h("sin detalle", "no details", "sem detalhes")
                self._log(self._h(f"✗ Error instalando Tap Mapper: {msg}", f"✗ Error installing Tap Mapper: {msg}", f"✗ Erro ao instalar o Tap Mapper: {msg}"))
                messagebox.showerror(self._h("Error al instalar Tap Mapper", "Error installing Tap Mapper", "Erro ao instalar o Tap Mapper"), msg)
        self.root.after(0, done)

    def _try_enable_tap_mapper_accessibility(self):
        """Intenta activar el servicio de accesibilidad via ADB sin que la
        persona tenga que tocar nada en el celular (truco conocido: 'adb
        shell settings put secure enabled_accessibility_services'). No
        funciona en todos los Android/fabricantes — si falla, no rompe nada,
        solo se le pide a la persona que lo active a mano (ver el mensaje
        que se muestra despues de instalar)."""
        try:
            _, out, _ = run_adb(["shell", "settings", "get", "secure",
                                  "enabled_accessibility_services"])
            current = (out or "").strip()
            services = [] if current in ("", "null") else current.split(":")
            if TAP_MAPPER_SERVICE not in services:
                services.append(TAP_MAPPER_SERVICE)
            new_value = ":".join(services)
            run_adb(["shell", "settings", "put", "secure",
                     "enabled_accessibility_services", new_value])
            run_adb(["shell", "settings", "put", "secure",
                     "accessibility_enabled", "1"])
            _, out2, _ = run_adb(["shell", "settings", "get", "secure",
                                   "enabled_accessibility_services"])
            return TAP_MAPPER_SERVICE in (out2 or "")
        except Exception:
            return False

    # ── SCRCPY ───────────────────────────────────────────────────
    def _build_cmd(self):
        scrcpy = self.scrcpy_var.get().strip() or "scrcpy"
        cmd    = [scrcpy]

        serial = self.selected_serial.get()
        # Solo usar -s si el serial es una IP:puerto (WiFi), no una entrada TLS
        if serial and (":" in serial or IP_RE.match(serial.split(":")[0])):
            cmd += ["-s", serial]
        elif serial and "_adb-tls" not in serial:
            cmd += ["-s", serial]

        fps = self.fps_var.get()
        if fps.isdigit():
            cmd += ["--max-fps", fps]

        bit = self.bitrate_var.get()
        if bit:
            cmd += ["--video-bit-rate", bit]

        res = self.res_var.get()
        if res and res != "0" and res.isdigit():
            cmd += ["--max-size", res]

        vcodec = self.vcodec_var.get()
        if vcodec and vcodec != "h264":
            cmd += ["--video-codec", vcodec]

        vbuf = self.vbuf_var.get()
        if vbuf and vbuf != "0" and vbuf.isdigit():
            cmd += ["--video-buffer", vbuf]

        if self.chk_audio.get():
            cmd += ["--audio-codec", self.codec_var.get()]
            abuf = self.abuf_var.get()
            if abuf and abuf != "0" and abuf.isdigit():
                cmd += ["--audio-buffer", abuf]
        else:
            cmd += ["--no-audio"]

        title = self.title_var.get().strip() or "MirrorDeck"
        cmd += ["--window-title", title]

        if self.chk_touches.get():    cmd += ["--show-touches"]
        if self.chk_awake.get():      cmd += ["--stay-awake"]
        if self.chk_borderless.get(): cmd += ["--window-borderless"]
        if self.chk_ontop.get():      cmd += ["--always-on-top"]
        if self.chk_gamepad.get():    cmd += ["--gamepad=uhid"]

        if self._rec_info:
            cmd += ["--record", str(self._rec_info["scrcpy_record_path"])]

        return cmd

    # ── GRABACION: preparar rutas, mic en paralelo y merge final ───
    def _prepare_recording(self):
        """Decide los nombres de archivo para esta corrida y, si hace falta
        mezclar microfono, arma rutas temporales por separado. Se llama
        justo antes de _build_cmd() para que --record apunte al lugar
        correcto (temporal si hay que mezclar, final si no)."""
        self._rec_info = None
        if not self.chk_record.get():
            return
        rec_dir = Path(self.record_dir_var.get().strip()
                        or (Path.home() / "Videos" / "MirrorDeck"))
        try:
            rec_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._log(self._h(f"⚠ No se pudo preparar la carpeta de grabacion: {e}",
                               f"⚠ Could not prepare the recording folder: {e}",
                               f"⚠ Nao foi possivel preparar a pasta de gravacao: {e}"))
            return
        ts = time.strftime("%Y%m%d_%H%M%S")
        final_path = rec_dir / f"mirror_{ts}.mkv"
        want_mic = self.chk_mic.get() and self.mic_device_var.get().strip()
        if want_mic:
            self._rec_info = {
                "scrcpy_record_path": rec_dir / f".tmp_phone_{ts}.mkv",
                "mic_tmp_path":       rec_dir / f".tmp_mic_{ts}.wav",
                "final_path":         final_path,
                "needs_merge":        True,
                "had_phone_audio":    self.chk_audio.get(),
            }
        else:
            self._rec_info = {
                "scrcpy_record_path": final_path,
                "needs_merge": False,
            }

    def _start_mic_recording(self):
        device = self.mic_device_var.get().strip()
        rec_info = self._rec_info
        if not device or not rec_info:
            return

        def go():
            try:
                ffmpeg = ensure_ffmpeg(log_cb=self._log)
            except Exception as e:
                self._log(self._h(f"✗ No se pudo preparar FFmpeg para el microfono: {e}",
                                   f"✗ Could not prepare FFmpeg for the microphone: {e}",
                                   f"✗ Nao foi possivel preparar o FFmpeg para o microfone: {e}"))
                self._log(self._h("  Se sigue grabando solo con audio/video del celular.",
                                   "  Still recording with just the phone's audio/video.",
                                   "  A gravacao continua so com audio/video do celular."))
                rec_info["needs_merge"] = False
                return
            cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            cmd = [ffmpeg, "-y", "-f", "dshow", "-i", f"audio={device}",
                   str(rec_info["mic_tmp_path"])]
            try:
                self.mic_proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, creationflags=cf)
                self._log(self._h("✓ Grabando microfono en paralelo.", "✓ Recording microphone in parallel.", "✓ Gravando microfone em paralelo."))
            except Exception as e:
                self._log(self._h(f"✗ No se pudo grabar el microfono: {e}",
                                   f"✗ Could not record the microphone: {e}",
                                   f"✗ Nao foi possivel gravar o microfone: {e}"))
                rec_info["needs_merge"] = False
        threading.Thread(target=go, daemon=True).start()

    def _stop_mic_recording(self):
        proc = self.mic_proc
        self.mic_proc = None
        if not proc or proc.poll() is not None:
            return
        try:
            proc.stdin.write(b"q")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

    def _merge_recording_bg(self, rec_info):
        self._log(self._h("→ Combinando grabacion (celular + microfono) en un solo archivo...",
                           "→ Merging recording (phone + microphone) into a single file...",
                           "→ Combinando gravacao (celular + microfone) em um unico arquivo..."))
        phone = Path(rec_info["scrcpy_record_path"])
        mic   = Path(rec_info["mic_tmp_path"])
        final = Path(rec_info["final_path"])

        if not phone.exists():
            self._log(self._h("✗ No se genero el archivo del celular; no hay nada para combinar.",
                               "✗ The phone's file wasn't generated; nothing to merge.",
                               "✗ O arquivo do celular nao foi gerado; nao ha nada para combinar."))
            return
        if not mic.exists():
            try:
                phone.rename(final)
            except Exception as e:
                self._log(self._h(f"✗ No se pudo guardar la grabacion: {e}",
                                   f"✗ Could not save the recording: {e}",
                                   f"✗ Nao foi possivel salvar a gravacao: {e}"))
                return
            self._log(self._h(f"⚠ El microfono no grabo nada; se guardo solo lo del celular: {final.name}",
                               f"⚠ The microphone didn't record anything; only the phone's was saved: {final.name}",
                               f"⚠ O microfone nao gravou nada; foi salvo apenas o do celular: {final.name}"))
            return

        try:
            ffmpeg = ensure_ffmpeg(log_cb=self._log)
        except Exception as e:
            self._log(self._h(f"✗ No se pudo preparar FFmpeg para combinar: {e}",
                               f"✗ Could not prepare FFmpeg to merge: {e}",
                               f"✗ Nao foi possivel preparar o FFmpeg para combinar: {e}"))
            self._log(self._h(f"  Quedaron los archivos sueltos: {phone.name} y {mic.name}",
                               f"  The separate files remain: {phone.name} and {mic.name}",
                               f"  Os arquivos separados permanecem: {phone.name} e {mic.name}"))
            return

        cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        if rec_info.get("had_phone_audio", True):
            filt = "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=3[aout]"
            cmd = [ffmpeg, "-y", "-i", str(phone), "-i", str(mic),
                   "-filter_complex", filt, "-map", "0:v", "-map", "[aout]",
                   "-c:v", "copy", "-c:a", "aac", str(final)]
        else:
            cmd = [ffmpeg, "-y", "-i", str(phone), "-i", str(mic),
                   "-map", "0:v", "-map", "1:a",
                   "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                                creationflags=cf, timeout=600)
        except Exception as e:
            self._log(self._h(f"✗ Error combinando audio/video: {e}", f"✗ Error merging audio/video: {e}", f"✗ Erro ao combinar audio/video: {e}"))
            self._log(self._h(f"  Quedaron los archivos sueltos: {phone.name} y {mic.name}",
                               f"  The separate files remain: {phone.name} and {mic.name}",
                               f"  Os arquivos separados permanecem: {phone.name} e {mic.name}"))
            return

        if r.returncode == 0 and final.exists():
            for f in (phone, mic):
                try:
                    f.unlink()
                except Exception:
                    pass
            self._log(self._h(f"✓ Grabacion lista: {final.name}", f"✓ Recording ready: {final.name}", f"✓ Gravacao pronta: {final.name}"))
        else:
            err = (r.stderr or "")[-400:]
            self._log(self._h(f"✗ Error combinando audio/video: {err}", f"✗ Error merging audio/video: {err}", f"✗ Erro ao combinar audio/video: {err}"))
            self._log(self._h(f"  Quedaron los archivos sueltos: {phone.name} y {mic.name}",
                               f"  The separate files remain: {phone.name} and {mic.name}",
                               f"  Os arquivos separados permanecem: {phone.name} e {mic.name}"))

    def _start_mirror(self):
        status, _ = self._license_status()
        if status == "expired":
            self._show_license_gate()
            return
        if not self.devices:
            messagebox.showwarning(self._h("Sin dispositivo", "No device", "Sem dispositivo"),
                                   self._h("Primero conecta el celular por WiFi.",
                                           "First connect the phone via WiFi.",
                                           "Primeiro conecte o celular por WiFi."))
            return
        if self.mirror_active:
            messagebox.showinfo(self._h("Activo", "Active", "Ativo"),
                                 self._h("El mirror ya esta corriendo.", "The mirror is already running.", "O mirror ja esta rodando."))
            return
        self._save_config()
        self._prepare_recording()
        cmd = self._build_cmd()
        self._log(f"→ {' '.join(cmd)}")
        try:
            cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.mirror_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, creationflags=cf)
            self.mirror_active = True
            self._set_status(self._h("Mirror activo ▶", "Mirror active ▶", "Mirror ativo ▶"), GREEN)
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self._log(self._h("✓ Mirror activo.", "✓ Mirror active.", "✓ Mirror ativo."))
            if self._rec_info and self._rec_info.get("needs_merge"):
                self._start_mic_recording()
            threading.Thread(target=self._watch_proc, daemon=True).start()
        except FileNotFoundError:
            self._log(self._h("✗ scrcpy no encontrado.", "✗ scrcpy not found.", "✗ scrcpy nao encontrado."))
            messagebox.showerror(self._h("scrcpy no encontrado", "scrcpy not found", "scrcpy nao encontrado"),
                self._h("Instala con:\n  winget install Genymobile.scrcpy",
                        "Install with:\n  winget install Genymobile.scrcpy",
                        "Instale com:\n  winget install Genymobile.scrcpy"))
        except Exception as e:
            self._log(f"✗ {e}")

    def _watch_proc(self):
        try:
            for line in self.mirror_proc.stdout:
                line = line.strip()
                if line:
                    self._log(f"  {line}")
            self.mirror_proc.wait()
        except Exception:
            pass
        finally:
            self.mirror_active = False
            self.root.after(0, self._on_stopped)

    def _on_stopped(self):
        self._set_status(self._h("Mirror detenido", "Mirror stopped", "Mirror parado"), TEXT_DIM)
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._log(self._h("⏹ Mirror detenido.", "⏹ Mirror stopped.", "⏹ Mirror parado."))

        rec_info = self._rec_info
        self._rec_info = None
        if rec_info:
            self._stop_mic_recording()
            if rec_info.get("needs_merge"):
                threading.Thread(target=self._merge_recording_bg,
                                  args=(rec_info,), daemon=True).start()
            else:
                self._log(self._h(f"✓ Grabacion guardada: {Path(rec_info['scrcpy_record_path']).name}",
                                   f"✓ Recording saved: {Path(rec_info['scrcpy_record_path']).name}",
                                   f"✓ Gravacao salva: {Path(rec_info['scrcpy_record_path']).name}"))

        if self.pending_restart:
            self.pending_restart = False
            self.root.after(300, self._start_mirror)

    def _stop_mirror(self):
        if self.mirror_proc and self.mirror_active:
            try:
                self.mirror_proc.terminate()
            except Exception:
                pass

    # ── REINICIO AUTOMATICO AL CAMBIAR AJUSTES ──────────────────────
    # scrcpy solo lee --max-size, --max-fps, --video-bit-rate, buffers, etc.
    # al arrancar el proceso: cambiarlos en la UI mientras el mirror ya
    # esta corriendo no tiene ningun efecto hasta reiniciarlo. Por eso la
    # resolucion "no cambiaba": el proceso viejo seguia corriendo con el
    # comando original. Esto detecta el cambio y reinicia solo.
    def _on_setting_change(self, *_):
        if not self.mirror_active:
            return
        if self.restart_job:
            self.root.after_cancel(self.restart_job)
        self.restart_job = self.root.after(600, self._trigger_restart)

    def _trigger_restart(self):
        self.restart_job = None
        if not self.mirror_active:
            return
        self._log(self._h("🔄 Configuracion cambiada. Reiniciando mirror para aplicarla...",
                           "🔄 Settings changed. Restarting mirror to apply it...",
                           "🔄 Configuracao alterada. Reiniciando o mirror para aplicar..."))
        self.pending_restart = True
        self._stop_mirror()

    # ── OBS HELP ─────────────────────────────────────────────────
    def _obs_help(self):
        win = tk.Toplevel(self.root)
        win.title(self._h("Como capturar en OBS", "How to capture in OBS", "Como capturar no OBS"))
        win.geometry("480x320")
        win.configure(bg=BG)
        win.grab_set()
        tk.Label(win, text=self._h("Como capturar en OBS Studio", "How to capture in OBS Studio", "Como capturar no OBS Studio"),
                 bg=BG, fg=TEXT, font=FONT_B).pack(pady=(14, 4))
        title = self.title_var.get() or "MirrorDeck"
        txt = scrolledtext.ScrolledText(win, bg=BG2, fg=TEXT,
                                         font=("Segoe UI", 9),
                                         relief="flat", wrap="word")
        if self.lang == "en":
            txt.insert("1.0", f"""
SCREEN:
  1. Start the mirror (▶ Start Mirror)
  2. OBS: Sources → [+] → Window Capture
     → Window: [{title}]
     → Method: Windows Graphics Capture
  3. Adjust the size in the preview

AUDIO:
  Easy option: "Desktop Audio Capture"
  captures all system audio including the phone's.

  Specific option: Sources → [+] → Audio Input Capture
  → look for "scrcpy" in the device list.
""")
        elif self.lang == "pt":
            txt.insert("1.0", f"""
TELA:
  1. Inicie o mirror (▶ Iniciar Mirror)
  2. OBS: Fontes → [+] → Captura de janela
     → Janela: [{title}]
     → Metodo: Windows Graphics Capture
  3. Ajuste o tamanho na pre-visualizacao

AUDIO:
  Opcao facil: "Captura de audio da area de trabalho"
  captura todo o audio do sistema, incluindo o do celular.

  Opcao especifica: Fontes → [+] → Captura de entrada de audio
  → procure "scrcpy" na lista de dispositivos.
""")
        else:
            txt.insert("1.0", f"""
PANTALLA:
  1. Inicia el mirror (▶ Iniciar Mirror)
  2. OBS: Fuentes → [+] → Captura de ventana
     → Ventana: [{title}]
     → Metodo: Windows Graphics Capture
  3. Ajusta el tamanio en la vista previa

AUDIO:
  Opcion facil: "Captura de audio de escritorio"
  captura todo el audio del sistema incluyendo el del celular.

  Opcion especifica: Fuentes → [+] → Captura de audio de entrada
  → busca "scrcpy" en la lista de dispositivos.
""")
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True, padx=10, pady=6)
        tk.Button(win, text=self._h("Cerrar", "Close", "Fechar"), command=win.destroy,
                   bg=BG3, fg=TEXT, relief="flat", font=FONT).pack(pady=(0, 10))

    # ── COMENTARIOS / REPORTES ──────────────────────────────────
    def _open_feedback(self):
        win = tk.Toplevel(self.root)
        win.title(self._h("Enviar comentario / reportar un error", "Send feedback / report a bug", "Enviar comentario / reportar um erro"))
        win.configure(bg=BG)
        win.geometry("480x440")
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=self._h("Comentario, sugerencia o error", "Feedback, suggestion or bug", "Comentario, sugestao ou erro"),
                 bg=BG, fg=TEXT, font=FONT_B).pack(padx=16, pady=(14, 4), anchor="w")
        tk.Label(win,
                  text=self._h(
                       "Contanos que paso, que esperabas que pasara, y en que "
                       "parte de la app estabas. Si podes, adjunta una captura "
                       "de pantalla (Windows + Mayus + S para sacarla antes).",
                       "Tell us what happened, what you expected instead, and "
                       "what part of the app you were in. If you can, attach a "
                       "screenshot (Windows + Shift + S to take one first).",
                       "Conte para nos o que aconteceu, o que voce esperava que "
                       "acontecesse, e em que parte do app voce estava. Se "
                       "puder, anexe uma captura de tela (Windows + Shift + S "
                       "para tirar uma antes)."),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8),
                  justify="left", wraplength=440).pack(padx=16, anchor="w")

        txt = scrolledtext.ScrolledText(win, bg=BG2, fg=TEXT, font=FONT,
                                         relief="flat", wrap="word", height=10)
        txt.pack(fill="both", expand=True, padx=16, pady=(8, 4))

        attachment = {"path": None}
        att_lbl = tk.Label(win, text=self._h("Sin captura adjunta", "No screenshot attached", "Sem captura anexada"), bg=BG, fg=TEXT_DIM,
                            font=("Segoe UI", 8))
        att_lbl.pack(padx=16, anchor="w")

        def attach():
            path = filedialog.askopenfilename(
                title=self._h("Elegi una captura de pantalla", "Choose a screenshot", "Escolha uma captura de tela"),
                filetypes=[(self._h("Imagenes", "Images", "Imagens"), "*.png *.jpg *.jpeg *.gif *.bmp"),
                           (self._h("Todos los archivos", "All files", "Todos os arquivos"), "*.*")])
            if path:
                attachment["path"] = path
                att_lbl.config(text=self._h(f"Adjunto: {Path(path).name}", f"Attached: {Path(path).name}", f"Anexado: {Path(path).name}"), fg=GREEN)

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=(6, 4))
        self._btn(btn_row, self._h("📎 Adjuntar captura...", "📎 Attach screenshot...", "📎 Anexar captura..."), attach, YELLOW).pack(side="left")

        def send():
            body = txt.get("1.0", "end").strip()
            if not body:
                messagebox.showwarning(
                    self._h("Falta el texto", "Missing text", "Falta o texto"),
                    self._h("Escribi algo antes de enviar.", "Write something before sending.", "Escreva algo antes de enviar."))
                return
            self._send_feedback(body, attachment["path"])
            win.destroy()

        self._btn(win, self._h("✉  Enviar", "✉  Send", "✉  Enviar"), send, GREEN, big=True).pack(
            fill="x", padx=16, pady=(6, 14))

    def _send_feedback(self, body, attachment_path):
        """Arma un mailto: pre-cargado (texto + ultimas lineas del log) y,
        si hay una captura adjunta, la copia a una carpeta y la abre para
        que la persona la arrastre al correo — mailto: no permite adjuntar
        archivos solo. A proposito NO se manda nada por SMTP embebido en
        la app: guardar una contrasenia de correo dentro de un ejecutable
        que se distribuye a desconocidos no es seguro."""
        out_dir = (Path.home() / "Documents" / "MirrorDeck" / "Reportes"
                   / time.strftime("%Y%m%d_%H%M%S"))
        saved = False
        if attachment_path and Path(attachment_path).exists():
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(attachment_path, out_dir / Path(attachment_path).name)
                saved = True
            except Exception as e:
                self._log(self._h(f"⚠ No se pudo preparar el adjunto: {e}",
                                   f"⚠ Could not prepare the attachment: {e}",
                                   f"⚠ Nao foi possivel preparar o anexo: {e}"))

        try:
            log_content = self.log_box.get("1.0", "end").strip()
            log_excerpt = "\n".join(log_content.splitlines()[-25:])
        except Exception:
            log_excerpt = ""

        full_body = body
        if log_excerpt:
            full_body += self._h("\n\n--- Ultimas lineas del log ---\n",
                                  "\n\n--- Last log lines ---\n",
                                  "\n\n--- Ultimas linhas do log ---\n") + log_excerpt
        if saved:
            full_body += self._h(
                "\n\n(Se abrio una carpeta con la captura — "
                "arrastrala a este correo antes de enviarlo)",
                "\n\n(A folder with the screenshot was opened — "
                "drag it into this email before sending)",
                "\n\n(Uma pasta com a captura foi aberta — "
                "arraste-a para este e-mail antes de enviar)")
        full_body = full_body[:1800]  # los links mailto: tienen largo limitado

        mailto = (f"mailto:{FEEDBACK_EMAIL}"
                  f"?subject={urllib.parse.quote('MirrorDeck - Comentario / Reporte')}"
                  f"&body={urllib.parse.quote(full_body)}")
        try:
            webbrowser.open(mailto)
        except Exception as e:
            self._log(self._h(f"✗ No se pudo abrir el cliente de correo: {e}",
                               f"✗ Could not open the email client: {e}",
                               f"✗ Nao foi possivel abrir o cliente de e-mail: {e}"))
            messagebox.showerror(
                "Error", self._h(
                    f"No se pudo abrir el cliente de correo:\n{e}\n\n"
                    f"Podes escribir directamente a {FEEDBACK_EMAIL}",
                    f"Could not open the email client:\n{e}\n\n"
                    f"You can write directly to {FEEDBACK_EMAIL}",
                    f"Nao foi possivel abrir o cliente de e-mail:\n{e}\n\n"
                    f"Voce pode escrever diretamente para {FEEDBACK_EMAIL}"))
            return

        if saved:
            try:
                os.startfile(str(out_dir))
            except Exception:
                pass
            messagebox.showinfo(
                self._h("Casi listo", "Almost done", "Quase pronto"),
                self._h(
                    "Se abrio tu cliente de correo con el mensaje cargado, y una "
                    "carpeta con la captura adjunta.\n\n"
                    "Arrastra esa imagen al correo antes de enviarlo — el correo "
                    "no la adjunta solo.",
                    "Your email client opened with the message loaded, and a "
                    "folder with the screenshot.\n\n"
                    "Drag that image into the email before sending it — the "
                    "email doesn't attach it automatically.",
                    "Seu cliente de e-mail abriu com a mensagem carregada, e uma "
                    "pasta com a captura de tela.\n\n"
                    "Arraste essa imagem para o e-mail antes de envia-lo — o "
                    "e-mail nao a anexa sozinho."))
        self._log(self._h("→ Comentario/reporte preparado para enviar por correo.",
                           "→ Feedback/report ready to send by email.",
                           "→ Comentario/reporte pronto para enviar por e-mail."))

    # ── INSTRUCTIVO COMPLETO ─────────────────────────────────────
    def _show_instructivo(self):
        win = tk.Toplevel(self.root)
        win.title(self._h("Instructivo completo - MirrorDeck", "Full guide - MirrorDeck", "Guia completo - MirrorDeck"))
        win.geometry("620x640")
        win.configure(bg=BG)
        win.grab_set()

        hdr = tk.Frame(win, bg=BG3, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text=self._h("Instructivo completo", "Full guide", "Guia completo"),
                 font=("Segoe UI", 13, "bold"), bg=BG3, fg=TEXT).pack()
        tk.Label(hdr, text=self._h("Todo lo que necesitas saber para usar MirrorDeck",
                                    "Everything you need to know to use MirrorDeck",
                                    "Tudo o que voce precisa saber para usar o MirrorDeck"),
                 font=("Segoe UI", 9), bg=BG3, fg=TEXT_DIM).pack()

        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=2)
        canvas = tk.Canvas(frame, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        # Scroll con rueda del mouse
        canvas.bind_all("<MouseWheel>",
                         lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        def sec(title, color=GREEN):
            tk.Label(inner, text=title, font=("Segoe UI", 11, "bold"),
                     bg=BG, fg=color, anchor="w").pack(fill="x", padx=16, pady=(14, 2))
            tk.Frame(inner, bg=color, height=1).pack(fill="x", padx=16)

        def item(text, indent=0, color=TEXT):
            tk.Label(inner, text=text, font=("Segoe UI", 9),
                     bg=BG, fg=color, anchor="w", justify="left",
                     wraplength=540).pack(fill="x", padx=(16 + indent*16, 16), pady=1)

        def sp():
            tk.Label(inner, text="", bg=BG, height=1).pack()

        def T(es, en, pt=None):
            return self._h(es, en, pt)

        sec(T("Requisitos previos", "Prerequisites", "Pre-requisitos"))
        item(T("• Android 11 o superior para depuracion inalambrica",
               "• Android 11 or higher for wireless debugging",
               "• Android 11 ou superior para depuracao sem fio"))
        item(T("• Android 10 o menor: conectar por USB primero (ver abajo)",
               "• Android 10 or lower: connect via USB first (see below)",
               "• Android 10 ou inferior: conecte por USB primeiro (veja abaixo)"))
        item(T("• Celular y PC en la MISMA red WiFi", "• Phone and PC on the SAME WiFi network",
               "• Celular e PC na MESMA rede WiFi"))
        item(T("• ADB y scrcpy instalados (el instalador los instala automaticamente)",
               "• ADB and scrcpy installed (the installer installs them automatically)",
               "• ADB e scrcpy instalados (o instalador os instala automaticamente)"))

        sec(T("Primera conexion — Android 11+", "First connection — Android 11+", "Primeira conexao — Android 11+"))
        item(T("💡 Tip: el boton '🔍 Buscar' (junto a IP/Puerto, en Emparejar y en Conectar) "
               "detecta el celular solo en la red y completa la IP y el puerto por vos — "
               "en los pasos de abajo, solo vas a tener que leer el codigo de 6 digitos.",
               "💡 Tip: the '🔍 Search' button (next to IP/Port, in Pair and in Connect) "
               "auto-detects the phone on the network and fills in the IP and port for you — "
               "in the steps below, you'll only need to read the 6-digit code.",
               "💡 Dica: o botao '🔍 Buscar' (ao lado de IP/Porta, em Parear e em Conectar) "
               "detecta o celular sozinho na rede e preenche o IP e a porta por voce — "
               "nos passos abaixo, voce so vai precisar ler o codigo de 6 digitos."),
             color=GREEN)
        sp()
        item(T("PASO 1: Activar opciones de desarrollador", "STEP 1: Enable developer options", "PASSO 1: Ativar opcoes do desenvolvedor"), color=YELLOW)
        item(T("1. Ajustes → Acerca del telefono", "1. Settings → About phone", "1. Configuracoes → Sobre o telefone"), 1)
        item(T("2. Toca 'Numero de compilacion' 7 veces seguidas",
               "2. Tap 'Build number' 7 times in a row",
               "2. Toque em 'Numero da versao' 7 vezes seguidas"), 1)
        item(T("   Samsung: Ajustes → Acerca → Info de software → N° de compilacion",
               "   Samsung: Settings → About → Software info → Build number",
               "   Samsung: Configuracoes → Sobre → Informacoes de software → Numero da versao"), 1, TEXT_DIM)
        item(T("   Xiaomi: toca 'Version de MIUI' en lugar del numero de compilacion",
               "   Xiaomi: tap 'MIUI version' instead of the build number",
               "   Xiaomi: toque em 'Versao da MIUI' em vez do numero da versao"), 1, TEXT_DIM)
        item(T("   Motorola: el numero de compilacion esta directo en 'Acerca del telefono'",
               "   Motorola: the build number is right in 'About phone'",
               "   Motorola: o numero da versao fica direto em 'Sobre o telefone'"), 1, TEXT_DIM)
        item(T("3. Ingresa tu PIN si te lo pide", "3. Enter your PIN if asked", "3. Digite seu PIN se for solicitado"), 1)
        item(T("4. Ves el mensaje 'Ahora eres desarrollador'", "4. You'll see 'You are now a developer'",
               "4. Voce vera a mensagem 'Agora voce e um desenvolvedor'"), 1)
        sp()
        item(T("PASO 2: Activar depuracion inalambrica", "STEP 2: Enable wireless debugging", "PASSO 2: Ativar a depuracao sem fio"), color=YELLOW)
        item(T("1. Ajustes → Opciones de desarrollador", "1. Settings → Developer options", "1. Configuracoes → Opcoes do desenvolvedor"), 1)
        item(T("   (puede estar en Sistema → Opciones de desarrollador en algunos celulares)",
               "   (may be under System → Developer options on some phones)",
               "   (pode estar em Sistema → Opcoes do desenvolvedor em alguns celulares)"), 1, TEXT_DIM)
        item(T("2. Activa 'Depuracion inalambrica'", "2. Turn on 'Wireless debugging'", "2. Ative a 'Depuracao sem fio'"), 1)
        item(T("3. Toca el TEXTO 'Depuracion inalambrica' (no el interruptor)",
               "3. Tap the TEXT 'Wireless debugging' (not the switch)",
               "3. Toque no TEXTO 'Depuracao sem fio' (nao no interruptor)"), 1)
        item(T("4. Anota la IP y el PUERTO que aparecen (ej: 192.168.1.105 : 33973)",
               "4. Note the IP and PORT shown (e.g. 192.168.1.105 : 33973)",
               "4. Anote o IP e a PORTA que aparecem (ex: 192.168.1.105 : 33973)"), 1)
        sp()
        item(T("PASO 3: Emparejar la PC (solo la primera vez)", "STEP 3: Pair the PC (first time only)", "PASSO 3: Parear o PC (somente na primeira vez)"), color=YELLOW)
        item(T("1. En la misma pantalla toca 'Vincular con codigo de vinculacion'",
               "1. On the same screen tap 'Pair device with pairing code'",
               "1. Na mesma tela, toque em 'Parear dispositivo com codigo de pareamento'"), 1)
        item(T("2. Aparece un codigo de 6 digitos y un PUERTO DIFERENTE (ej: 45533)",
               "2. A 6-digit code and a DIFFERENT PORT appear (e.g. 45533)",
               "2. Aparece um codigo de 6 digitos e uma PORTA DIFERENTE (ex: 45533)"), 1)
        item(T("3. En MirrorDeck, seccion 'Emparejar':", "3. In MirrorDeck, 'Pair' section:", "3. No MirrorDeck, secao 'Parear':"), 1)
        item(T("   IP: la IP de tu celular  |  Puerto vinc.: el puerto de vinculacion",
               "   IP: your phone's IP  |  Pairing port: the pairing port",
               "   IP: o IP do seu celular  |  Porta de pareamento: a porta de pareamento"), 2, TEXT_DIM)
        item(T("   Codigo: el codigo de 6 digitos", "   Code: the 6-digit code", "   Codigo: o codigo de 6 digitos"), 2, TEXT_DIM)
        item(T("4. Clic en 'Emparejar' → aparece 'Emparejado correctamente'",
               "4. Click 'Pair' → 'Paired successfully' appears",
               "4. Clique em 'Parear' → aparece 'Pareado com sucesso'"), 1)
        sp()
        item(T("PASO 4: Conectar", "STEP 4: Connect", "PASSO 4: Conectar"), color=YELLOW)
        item(T("1. IP del celular: la misma IP de antes", "1. Phone IP: the same IP as before", "1. IP do celular: o mesmo IP de antes"), 1)
        item(T("2. Puerto: el puerto de DEPURACION (ej: 33973) — NO el de vinculacion",
               "2. Port: the DEBUGGING port (e.g. 33973) — NOT the pairing one",
               "2. Porta: a porta de DEPURACAO (ex: 33973) — NAO a de pareamento"), 1)
        item(T("3. Clic en 'Conectar'", "3. Click 'Connect'", "3. Clique em 'Conectar'"), 1)
        item(T("4. El celular aparece en la lista de dispositivos",
               "4. The phone shows up in the device list",
               "4. O celular aparece na lista de dispositivos"), 1)

        sec(T("Uso diario (despues del primer emparejamiento)", "Daily use (after the first pairing)", "Uso diario (depois do primeiro pareamento)"))
        item(T("1. Abre MirrorDeck", "1. Open MirrorDeck", "1. Abra o MirrorDeck"))
        item(T("2. La app intenta reconectar automaticamente al ultimo celular",
               "2. The app tries to automatically reconnect to the last phone",
               "2. O app tenta reconectar automaticamente ao ultimo celular"))
        item(T("3. Si no conecta: ingresa IP y puerto y clic 'Conectar'",
               "3. If it doesn't connect: enter IP and port and click 'Connect'",
               "3. Se nao conectar: digite IP e porta e clique em 'Conectar'"))
        item(T("4. Selecciona el dispositivo en la lista", "4. Select the device in the list", "4. Selecione o dispositivo na lista"))
        item(T("5. Clic en ▶ Iniciar Mirror", "5. Click ▶ Start Mirror", "5. Clique em ▶ Iniciar Mirror"))
        item(T("6. En OBS: Fuentes → [+] → Captura de ventana → 'MirrorDeck'",
               "6. In OBS: Sources → [+] → Window Capture → 'MirrorDeck'",
               "6. No OBS: Fontes → [+] → Captura de janela → 'MirrorDeck'"))
        sp()
        item(T("IMPORTANTE: el PUERTO de depuracion cambia cada vez que se",
               "IMPORTANT: the debugging PORT changes every time",
               "IMPORTANTE: a PORTA de depuracao muda toda vez que a"), color=YELLOW)
        item(T("activa 'Depuracion inalambrica' en el celular (seguridad de",
               "'Wireless debugging' is turned on on the phone (Android",
               "'Depuracao sem fio' e ativada no celular (seguranca do"), color=YELLOW)
        item(T("Android, no es un error). Casi siempre hay que volver a mirarlo",
               "security, not a bug). You'll almost always need to check it",
               "Android, nao e um erro). Quase sempre e preciso olhar de novo"), color=YELLOW)
        item(T("en el celular y actualizarlo en el Paso 1 antes de conectar.",
               "again on the phone and update it in Step 1 before connecting.",
               "no celular e atualizar no Passo 1 antes de conectar."), color=YELLOW)
        item(T("La IP en cambio suele quedar igual mientras no cambies de WiFi.",
               "The IP, on the other hand, usually stays the same as long as you don't switch WiFi.",
               "Ja o IP costuma ficar igual enquanto voce nao trocar de WiFi."), 1, TEXT_DIM)

        sec(T("Pantalla negra en bancos, Mercado Pago, Claro Video, etc.",
              "Black screen on banking apps, Mercado Pago, Claro Video, etc.",
              "Tela preta em apps de banco, Mercado Pago, Claro Video, etc."), RED)
        item(T("Esto NO es un error de la app. Android marca esas pantallas como",
               "This is NOT a bug in the app. Android flags those screens as",
               "Isso NAO e um erro do app. O Android marca essas telas como"), color=YELLOW)
        item(T("'protegidas' y bloquea cualquier mirror o grabacion, sin excepcion.",
               "'protected' and blocks any mirroring or recording, no exceptions.",
               "'protegidas' e bloqueia qualquer mirror ou gravacao, sem excecoes."), color=YELLOW)
        item(T("→  No tiene solucion sin root del celular. Es una proteccion del sistema.",
               "→  There's no fix without rooting the phone. It's a system-level protection.",
               "→  Nao tem solucao sem root do celular. E uma protecao do sistema."), 1, TEXT_DIM)
        item(T("→  El screenshot local SI funciona porque usa un mecanismo distinto.",
               "→  The local screenshot DOES work because it uses a different mechanism.",
               "→  A captura de tela local FUNCIONA porque usa um mecanismo diferente."), 1, TEXT_DIM)
        sp()

        sec(T("La depuracion inalambrica se apaga sola / el puerto cambia",
              "Wireless debugging turns off by itself / the port changes",
              "A depuracao sem fio desliga sozinha / a porta muda"), RED)
        item(T("Pasa porque el celular mata el servicio en segundo plano para",
               "Happens because the phone kills the background service to",
               "Acontece porque o celular mata o servico em segundo plano para"), color=YELLOW)
        item(T("ahorrar bateria. Es mas comun en marcas con Android muy",
               "save battery. It's more common on brands with heavily",
               "economizar bateria. E mais comum em marcas com Android muito"), color=YELLOW)
        item(T("personalizado: Xiaomi (MIUI), Oppo/Realme (ColorOS), Vivo",
               "customized Android: Xiaomi (MIUI), Oppo/Realme (ColorOS), Vivo",
               "personalizado: Xiaomi (MIUI), Oppo/Realme (ColorOS), Vivo"), color=YELLOW)
        item(T("(Funtouch OS), Huawei (EMUI) y chinas menos conocidas en general.",
               "(Funtouch OS), Huawei (EMUI), and lesser-known Chinese brands in general.",
               "(Funtouch OS), Huawei (EMUI) e marcas chinesas menos conhecidas em geral."), color=YELLOW)
        item(T("→  Ajustes → Bateria → Apps → busca 'ADB' o el servicio del sistema",
               "→  Settings → Battery → Apps → look for 'ADB' or the system service",
               "→  Configuracoes → Bateria → Apps → procure 'ADB' ou o servico do sistema"), 1, GREEN)
        item(T("    y desactiva la optimizacion de bateria para ese proceso si aparece",
               "    and turn off battery optimization for that process if it shows up",
               "    e desative a otimizacao de bateria para esse processo se aparecer"), 1, GREEN)
        item(T("→  Algunos celulares: Ajustes → Bateria → Sin restricciones para apps en 2do plano",
               "→  Some phones: Settings → Battery → No restrictions for background apps",
               "→  Alguns celulares: Configuracoes → Bateria → Sem restricoes para apps em 2° plano"), 1, GREEN)
        item(T("→  El PUERTO cambia SIEMPRE que se reactiva el toggle, aunque no",
               "→  The PORT ALWAYS changes when the toggle is turned back on, even if you",
               "→  A PORTA muda SEMPRE que o interruptor e reativado, mesmo que voce"), 1, TEXT_DIM)
        item(T("    hayas hecho nada raro — es normal, solo hay que actualizarlo",
               "    didn't do anything unusual — it's normal, just update it",
               "    nao tenha feito nada estranho — e normal, so precisa atualizar"), 1, TEXT_DIM)
        item(T("→  Algunos celulares (sobre todo con Android modificado) tambien",
               "→  Some phones (especially with modified Android) also",
               "→  Alguns celulares (principalmente com Android modificado) tambem"), 1, TEXT_DIM)
        item(T("    'olvidan' el EMPAREJAMIENTO al apagar el toggle o reiniciar,",
               "    'forget' the PAIRING when the toggle is turned off or after a restart,",
               "    'esquecem' o PAREAMENTO ao desligar o interruptor ou reiniciar,"), 1, TEXT_DIM)
        item(T("    no solo el puerto — si conectar falla, proba re-emparejar",
               "    not just the port — if connecting fails, try pairing again",
               "    nao so a porta — se a conexao falhar, tente parear de novo"), 1, TEXT_DIM)
        item(T("    de nuevo (seccion 'Emparejar') antes de asumir que algo se rompio",
               "    (the 'Pair' section) before assuming something broke",
               "    (secao 'Parear') antes de supor que algo quebrou"), 1, TEXT_DIM)
        sp()

        sec(T("Joystick / Gamepad", "Joystick / Gamepad", "Joystick / Gamepad"))
        item(T("Podes usar cualquier control conectado a la PC (USB o Bluetooth)",
               "You can use any controller connected to the PC (USB or Bluetooth)",
               "Voce pode usar qualquer controle conectado ao PC (USB ou Bluetooth)"))
        item(T("para jugar viendo la pantalla del celular en grande, en la PC.",
               "to play while watching the phone's screen enlarged on the PC.",
               "para jogar vendo a tela do celular ampliada no PC."))
        item(T("Compatible con: Xbox, PlayStation, Redragon y la mayoria de",
               "Compatible with: Xbox, PlayStation, Redragon and most",
               "Compativel com: Xbox, PlayStation, Redragon e a maioria dos"))
        item(T("controles genericos reconocidos por Windows.",
               "generic controllers recognized by Windows.",
               "controles genericos reconhecidos pelo Windows."))
        item(T("1. Conecta tu control a la PC antes de iniciar el mirror",
               "1. Connect your controller to the PC before starting the mirror",
               "1. Conecte seu controle ao PC antes de iniciar o mirror"), 1)
        item(T("2. Activa 'Usar joystick/control conectado a la PC'",
               "2. Turn on 'Use joystick/controller connected to the PC'",
               "2. Ative 'Usar joystick/controle conectado ao PC'"), 1)
        item(T("3. Iniciá el mirror normalmente", "3. Start the mirror normally", "3. Inicie o mirror normalmente"), 1)
        item(T("4. La primera vez, el celular puede pedir un permiso — aceptalo",
               "4. The first time, the phone may ask for a permission — accept it",
               "4. Na primeira vez, o celular pode pedir uma permissao — aceite"), 1)
        item(T("Nota: funciona en la mayoria de juegos que soportan control,",
               "Note: works in most games that support controllers,",
               "Nota: funciona na maioria dos jogos que suportam controle,"), 1, TEXT_DIM)
        item(T("pero algunos juegos pueden no reconocer el control virtual.",
               "but some games may not recognize the virtual controller.",
               "mas alguns jogos podem nao reconhecer o controle virtual."), 1, TEXT_DIM)
        sp()

        sec(T("Problemas comunes", "Common issues", "Problemas comuns"), RED)
        item(T("❌  'Protocol fault' o error despues de reiniciar la PC",
               "❌  'Protocol fault' or error after restarting the PC",
               "❌  'Protocol fault' ou erro depois de reiniciar o PC"), color=YELLOW)
        item(T("→  Clic en '↺ Reiniciar ADB' — resuelve el problema automaticamente",
               "→  Click '↺ Restart ADB' — fixes the problem automatically",
               "→  Clique em '↺ Reiniciar ADB' — resolve o problema automaticamente"), 1, GREEN)
        sp()
        item(T("❌  La imagen se pixela de golpe (como si bajara a 144p) sin razon",
               "❌  The image suddenly gets pixelated (as if it dropped to 144p) for no reason",
               "❌  A imagem fica pixelada do nada (como se caisse para 144p) sem motivo"), color=YELLOW)
        item(T("→  Es un bug conocido de Windows/SDL, no de tu WiFi ni del celular:",
               "→  This is a known Windows/SDL bug, not your WiFi or the phone:",
               "→  E um bug conhecido do Windows/SDL, nao do seu WiFi nem do celular:"), 1, GREEN)
        item(T("    pasa sobre todo despues de minimizar y restaurar la ventana del",
               "    it happens mostly after minimizing and restoring the mirror",
               "    acontece principalmente depois de minimizar e restaurar a janela"), 1, TEXT_DIM)
        item(T("    mirror — el area de dibujo no se re-sincroniza con el tamanio real",
               "    window — the drawing area doesn't re-sync with the window's real",
               "    do mirror — a area de desenho nao se re-sincroniza com o tamanho"), 1, TEXT_DIM)
        item(T("    de la ventana, asi que el video se ve 'estirado' desde un cuadro",
               "    size, so the video looks 'stretched' from a much smaller frame",
               "    real da janela, entao o video parece 'esticado' a partir de um"), 1, TEXT_DIM)
        item(T("    mucho mas chico, aunque el celular sigue transmitiendo bien.",
               "    even though the phone is still streaming fine.",
               "    quadro bem menor, mesmo o celular continuando a transmitir bem."), 1, TEXT_DIM)
        item(T("→  Arreglo rapido: arrastra un borde de la ventana para achicarla o",
               "→  Quick fix: drag a window edge to resize it slightly",
               "→  Solucao rapida: arraste uma borda da janela para diminuir ou"), 1, GREEN)
        item(T("    agrandarla apenas un pixel — se corrige al instante",
               "    (shrink or grow by a pixel) — it fixes itself instantly",
               "    aumentar apenas um pixel — se corrige na hora"), 1, GREEN)
        item(T("→  Si no, Detener Mirror e Iniciar Mirror de nuevo tambien lo soluciona",
               "→  Otherwise, Stop Mirror and Start Mirror again also fixes it",
               "→  Senao, Parar Mirror e Iniciar Mirror de novo tambem resolve"), 1, GREEN)
        sp()
        item(T("❌  Sin audio en OBS", "❌  No audio in OBS", "❌  Sem audio no OBS"), color=YELLOW)
        item(T("→  Verifica que 'Capturar audio del celular' este tildado en la app",
               "→  Check that 'Capture phone audio' is checked in the app",
               "→  Verifique se 'Capturar audio do celular' esta marcado no app"), 1, GREEN)
        item(T("→  Detén el mirror y volvé a iniciarlo", "→  Stop the mirror and start it again", "→  Pare o mirror e inicie de novo"), 1, GREEN)
        item(T("→  Si hay 2 dispositivos en ADB: clic en '↺ Reiniciar ADB'",
               "→  If there are 2 devices in ADB: click '↺ Restart ADB'",
               "→  Se houver 2 dispositivos no ADB: clique em '↺ Reiniciar ADB'"), 1, GREEN)
        item(T("→  En OBS usa 'Captura de audio de escritorio'",
               "→  In OBS use 'Desktop Audio Capture'",
               "→  No OBS use 'Captura de audio da area de trabalho'"), 1, GREEN)
        sp()
        item(T("❌  'Connection refused' o el celu rechaza la conexion",
               "❌  'Connection refused' or the phone rejects the connection",
               "❌  'Connection refused' ou o celular rejeita a conexao"), color=YELLOW)
        item(T("→  Puerto incorrecto. Verifica en Depuracion inalambrica del celu",
               "→  Wrong port. Check it in the phone's Wireless debugging screen",
               "→  Porta incorreta. Verifique na tela de Depuracao sem fio do celular"), 1, GREEN)
        item(T("→  Primera vez: necesitas emparejar primero (PASO 3)",
               "→  First time: you need to pair first (STEP 3)",
               "→  Primeira vez: voce precisa parear primeiro (PASSO 3)"), 1, GREEN)
        sp()
        item(T("❌  Android 10 o anterior", "❌  Android 10 or earlier", "❌  Android 10 ou anterior"), color=YELLOW)
        item(T("→  Conecta el celu por USB con Depuracion USB activada",
               "→  Connect the phone via USB with USB debugging enabled",
               "→  Conecte o celular por USB com a Depuracao USB ativada"), 1, GREEN)
        item(T("→  En CMD: adb tcpip 5555", "→  In CMD: adb tcpip 5555", "→  No CMD: adb tcpip 5555"), 1, GREEN)
        item(T("→  Desconecta el USB, ingresa la IP con puerto 5555 y conecta",
               "→  Unplug the USB, enter the IP with port 5555 and connect",
               "→  Desconecte o USB, digite o IP com a porta 5555 e conecte"), 1, GREEN)
        sp()

        tk.Button(win, text=self._h("Cerrar", "Close", "Fechar"), command=win.destroy,
                   bg=BG3, fg=TEXT, relief="flat", font=FONT,
                   padx=20, pady=6).pack(pady=10)

    # ── LICENCIA / PRUEBA GRATIS ─────────────────────────────────
    def _trial_days_left(self):
        first_run = self.config.get("first_run", "")
        if not first_run:
            return TRIAL_DAYS
        try:
            started = time.mktime(time.strptime(first_run, "%Y-%m-%d"))
        except Exception:
            return TRIAL_DAYS
        elapsed_days = (time.time() - started) / 86400
        return max(0, TRIAL_DAYS - int(elapsed_days))

    def _license_ok_cached(self):
        """True si hay una clave guardada que paso su ultima validacion
        online hace poco (con un margen de dias sin internet para no
        trabar a alguien que se quedo sin señal un rato)."""
        if not self.config.get("license_key"):
            return False
        last_ok = self.config.get("license_last_ok", "")
        if not last_ok:
            return False
        try:
            last_ts = time.mktime(time.strptime(last_ok, "%Y-%m-%d"))
        except Exception:
            return False
        return (time.time() - last_ts) / 86400 <= LICENSE_OFFLINE_GRACE_DAYS

    def _license_status(self):
        """('licensed', None) | ('trial', dias_restantes) | ('expired', None)"""
        if self._license_ok_cached():
            return ("licensed", None)
        days_left = self._trial_days_left()
        if days_left > 0:
            return ("trial", days_left)
        return ("expired", None)

    def _refresh_license_label(self):
        status, extra = self._license_status()
        if status == "licensed":
            self.license_lbl.config(text=self._h("🔑 Licencia activa", "🔑 License active", "🔑 Licenca ativa"), fg=GREEN)
        elif status == "trial":
            self.license_lbl.config(text=self._h(
                f"⏳ Prueba: {extra} dia(s) — click para activar",
                f"⏳ Trial: {extra} day(s) — click to activate",
                f"⏳ Teste: {extra} dia(s) — clique para ativar"), fg=YELLOW)
        else:
            self.license_lbl.config(text=self._h(
                "⚠ Prueba vencida — click para activar",
                "⚠ Trial expired — click to activate",
                "⚠ Teste vencido — clique para ativar"), fg=RED)

    def _open_license_dialog(self):
        win = tk.Toplevel(self.root)
        win.title(self._h("Licencia", "License", "Licenca"))
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)

        status, extra = self._license_status()
        if status == "trial":
            head = self._h(f"Prueba gratis: {extra} dia(s) restante(s)",
                            f"Free trial: {extra} day(s) left",
                            f"Teste gratis: {extra} dia(s) restante(s)")
        elif status == "licensed":
            head = self._h("Ya tenes una licencia activa", "You already have an active license", "Voce ja tem uma licenca ativa")
        else:
            head = self._h("Sin licencia activa", "No active license", "Sem licenca ativa")
        tk.Label(win, text=head, bg=BG, fg=TEXT, font=FONT_B).pack(padx=24, pady=(20, 4))
        tk.Label(win, text=self._h(
                  "¿Todavia no compraste? Elegi un plan (Mensual, Anual o "
                  "Fundador de por vida) en la tienda.",
                  "Haven't purchased yet? Pick a plan (Monthly, Yearly or "
                  "lifetime Founder) in the store.",
                  "Ainda nao comprou? Escolha um plano (Mensal, Anual ou "
                  "Fundador vitalicio) na loja."),
                  bg=BG, fg=TEXT_DIM, font=FONT, justify="center", wraplength=360).pack(
            padx=24, pady=(0, 12))

        self._btn(win, self._h("🛒 Ver planes / Comprar", "🛒 View plans / Buy", "🛒 Ver planos / Comprar"),
                   lambda: webbrowser.open(LEMONSQUEEZY_STORE_URL), GREEN, big=True).pack(
            padx=24, pady=(0, 14))

        tk.Frame(win, bg=BG3, height=1).pack(fill="x", padx=24, pady=(0, 14))

        tk.Label(win, text=self._h(
                  "¿Ya tenes una clave? (llega por correo al comprar)",
                  "Already have a key? (arrives by email after purchase)",
                  "Ja tem uma chave? (chega por e-mail apos a compra)"),
                  bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)).pack(padx=24, anchor="w")
        key_var = tk.StringVar(value=self.config.get("license_key", ""))
        tk.Entry(win, textvariable=key_var, bg=BG2, fg=TEXT,
                  insertbackground=TEXT, font=FONT, relief="flat", width=40).pack(
            padx=24, pady=(2, 10), fill="x")

        def do_activate():
            key = key_var.get().strip()
            if not key:
                return
            win.destroy()
            self._log(self._h("→ Activando licencia...", "→ Activating license...", "→ Ativando licenca..."))
            threading.Thread(target=self._activate_license_bg, args=(key,), daemon=True).start()

        self._btn(win, self._h("Activar clave", "Activate key", "Ativar chave"), do_activate, BLUE).pack(
            padx=24, pady=(0, 16))

        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _license_meta_matches(self, result):
        """Confirma que la clave sea de TU tienda/producto de Lemon
        Squeezy, no de cualquier otro producto de la plataforma (la API
        de licencias es publica y valida cualquier clave existente, asi
        que hay que chequear esto nosotros mismos). Si los IDs todavia
        estan en 0 (sin configurar), no bloquea nada — pero conviene
        completarlos antes de vender de verdad."""
        meta = result.get("meta") or {}
        store_ok = (not LEMONSQUEEZY_STORE_ID) or meta.get("store_id") == LEMONSQUEEZY_STORE_ID
        product_ok = (not LEMONSQUEEZY_PRODUCT_ID) or meta.get("product_id") == LEMONSQUEEZY_PRODUCT_ID
        return store_ok and product_ok

    def _activate_license_bg(self, key):
        instance_name = self.config.get("license_instance_id") or socket.gethostname()
        try:
            data = urllib.parse.urlencode({
                "license_key": key,
                "instance_name": instance_name,
            }).encode()
            req = urllib.request.Request(LEMONSQUEEZY_API_ACTIVATE, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
        except Exception as e:
            # OJO: capturamos str(e) en err_msg ANTES de armar el lambda.
            # Python borra la variable "e" del except al salir del bloque,
            # y como root.after() ejecuta el lambda mas tarde (diferido),
            # referenciar "e" directo adentro tira NameError en ese
            # momento — que Tkinter termina mostrando como "None" en el
            # cartel de error, en vez del mensaje real. Guardarlo en una
            # variable comun evita el problema.
            err_msg = str(e)
            self._log(self._h(f"✗ Error activando licencia: {err_msg}", f"✗ Error activating license: {err_msg}", f"✗ Erro ao ativar a licenca: {err_msg}"))
            self.root.after(0, lambda: messagebox.showerror(
                "Error", self._h(f"No se pudo activar la licencia (¿hay internet?):\n{err_msg}",
                                  f"Could not activate the license (do you have internet?):\n{err_msg}",
                                  f"Nao foi possivel ativar a licenca (tem internet?):\n{err_msg}")))
            return

        ok = bool(result.get("activated")) and self._license_meta_matches(result)

        def done():
            if ok:
                self.config["license_key"] = key
                self.config["license_instance_id"] = (
                    (result.get("instance") or {}).get("id", instance_name))
                self.config["license_last_ok"] = time.strftime("%Y-%m-%d")
                self._save_config()
                self._log(self._h("✓ Licencia activada correctamente.", "✓ License activated successfully.", "✓ Licenca ativada com sucesso."))
                self._refresh_license_label()
                messagebox.showinfo(self._h("Licencia activada", "License activated", "Licenca ativada"),
                                     self._h("Listo, tu licencia quedo activada.", "Done, your license is now active.", "Pronto, sua licenca esta ativada."))
            else:
                err = result.get("error", self._h(
                    "Clave invalida o ya usada en otro equipo", "Invalid key or already used on another device",
                    "Chave invalida ou ja usada em outro dispositivo"))
                self._log(self._h(f"✗ Licencia rechazada: {err}", f"✗ License rejected: {err}", f"✗ Licenca rejeitada: {err}"))
                if "activation limit" in str(err).lower():
                    # Mensaje mas humano para claves personales/de regalo con
                    # limite de 1 dispositivo: esto pasa tipicamente cuando la
                    # persona formateo/reinstalo Windows o cambio de PC. No
                    # hay forma de liberar el cupo automaticamente desde aca,
                    # asi que la guiamos a pedirle a quien le regalo la
                    # licencia que la libere (es un click en el panel de
                    # Lemon Squeezy, no necesita nada tecnico).
                    messagebox.showerror(
                        self._h("Limite de dispositivos alcanzado", "Device limit reached", "Limite de dispositivos atingido"),
                        self._h(
                            "Esta clave ya esta en uso en otro equipo.\n\n"
                            "Si formateaste o cambiaste de PC, pedile a quien te "
                            "dio la licencia que libere el dispositivo anterior "
                            "(es algo rapido de su lado) y volve a intentar.",
                            "This key is already in use on another device.\n\n"
                            "If you reformatted or switched PCs, ask whoever "
                            "gave you the license to release the previous "
                            "device (it's quick on their end) and try again.",
                            "Esta chave ja esta em uso em outro dispositivo.\n\n"
                            "Se voce formatou ou trocou de PC, peca para quem "
                            "te deu a licenca liberar o dispositivo anterior "
                            "(e rapido do lado dele) e tente novamente."))
                else:
                    messagebox.showerror(self._h("Licencia invalida", "Invalid license", "Licenca invalida"), err)
        self.root.after(0, done)

    def _validate_license_bg(self):
        """Re-chequea contra Lemon Squeezy que la licencia siga activa
        (por si se cancelo una suscripcion, por ejemplo). Corre en
        segundo plano al arrancar; si no hay internet simplemente no
        actualiza nada y se sigue usando el ultimo estado guardado
        (ver LICENSE_OFFLINE_GRACE_DAYS)."""
        key = self.config.get("license_key")
        if not key:
            return
        instance_id = self.config.get("license_instance_id", "")
        try:
            data = urllib.parse.urlencode({
                "license_key": key, "instance_id": instance_id}).encode()
            req = urllib.request.Request(LEMONSQUEEZY_API_VALIDATE, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            valid = bool(result.get("valid")) and self._license_meta_matches(result)
        except Exception:
            return
        if valid:
            self.config["license_last_ok"] = time.strftime("%Y-%m-%d")
            self._save_config()
        self.root.after(0, self._refresh_license_label)

    def _show_license_gate(self):
        win = tk.Toplevel(self.root)
        win.title(self._h("Prueba vencida", "Trial expired", "Teste vencido"))
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text=self._h("Se termino tu periodo de prueba", "Your trial period has ended", "Seu periodo de teste terminou"),
                 bg=BG, fg=TEXT, font=FONT_B).pack(padx=24, pady=(20, 6))
        tk.Label(win,
                  text=self._h(
                       f"Tuviste {TRIAL_DAYS} dias gratis para probar MirrorDeck.\n"
                       "Para seguir usandolo, activa una licencia.",
                       f"You had {TRIAL_DAYS} free days to try MirrorDeck.\n"
                       "To keep using it, activate a license.",
                       f"Voce teve {TRIAL_DAYS} dias gratis para testar o MirrorDeck.\n"
                       "Para continuar usando, ative uma licenca."),
                  bg=BG, fg=TEXT_DIM, font=FONT, justify="center", wraplength=360).pack(
            padx=24, pady=(0, 16))
        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=(0, 10))
        self._btn(btn_row, self._h("🛒 Comprar licencia", "🛒 Buy license", "🛒 Comprar licenca"),
                   lambda: webbrowser.open(LEMONSQUEEZY_STORE_URL), GREEN, big=True).pack(
            side="left", padx=6)
        self._btn(btn_row, self._h("🔑 Ya tengo una clave", "🔑 I already have a key", "🔑 Ja tenho uma chave"),
                   lambda: (win.destroy(), self._open_license_dialog()), BLUE, big=True).pack(
            side="left", padx=6)
        tk.Button(win, text=self._h("Cerrar", "Close", "Fechar"), command=win.destroy,
                   bg=BG3, fg=TEXT, relief="flat", font=FONT).pack(pady=(0, 18))

    # ── ACTUALIZACIONES ──────────────────────────────────────────
    def _check_for_update(self, silent=True):
        threading.Thread(target=self._check_for_update_bg, args=(silent,), daemon=True).start()

    def _check_for_update_bg(self, silent):
        try:
            req = urllib.request.Request(
                GITHUB_API_LATEST, headers={"User-Agent": "MirrorDeck"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            tag = (data.get("tag_name") or "").lstrip("vV")
            notes = data.get("body") or ""
            exe_asset = next(
                (a for a in data.get("assets", [])
                 if a.get("name", "").lower().endswith(".exe")), None)
        except Exception as e:
            err_msg = str(e)  # ver nota en _activate_license_bg sobre por que capturamos esto antes del lambda diferido
            if not silent:
                self.root.after(0, lambda: messagebox.showerror(
                    "Error", self._h(f"No se pudo chequear actualizaciones:\n{err_msg}",
                                      f"Could not check for updates:\n{err_msg}",
                                      f"Nao foi possivel verificar atualizacoes:\n{err_msg}")))
            return

        def ver_parts(v):
            return [int(x) for x in re.findall(r"\d+", v)]

        if tag and exe_asset and ver_parts(tag) > ver_parts(APP_VERSION):
            self._pending_update = {
                "tag": tag, "url": exe_asset["browser_download_url"], "notes": notes,
            }
            if silent:
                # Chequeo automatico de fondo: NUNCA interrumpe con un
                # popup ni cierra nada solo — imaginate estar en medio de
                # un stream y que la app te tire un cartel modal o, peor,
                # se cierre sin avisar. Solo se muestra un aviso chico y
                # descartable en el header; la persona decide cuando (y
                # si) instalar.
                self.root.after(0, lambda: self._show_update_banner(tag))
            else:
                # Chequeo manual (la persona toco "Buscar actualizacion"):
                # ahi si tiene sentido preguntar de una, porque el usuario
                # ya esta en ese momento de decision.
                def ask():
                    if messagebox.askyesno(
                            self._h("Actualizacion disponible", "Update available", "Atualizacao disponivel"),
                            self._h(
                                f"Hay una version nueva ({tag}, la tuya es {APP_VERSION}).\n\n"
                                "Se instala sola en segundo plano (sin pasos que completar) "
                                "y MirrorDeck se reabre solo con la version nueva.\n\n"
                                "¿Actualizar ahora?",
                                f"There's a new version ({tag}, yours is {APP_VERSION}).\n\n"
                                "It installs itself in the background (no steps to click "
                                "through) and MirrorDeck will reopen on its own with the "
                                "new version.\n\n"
                                "Update now?",
                                f"Ha uma versao nova ({tag}, a sua e {APP_VERSION}).\n\n"
                                "Ela se instala sozinha em segundo plano (sem passos para "
                                "clicar) e o MirrorDeck reabre sozinho com a versao nova.\n\n"
                                "Atualizar agora?")):
                        self._start_update_install()
                self.root.after(0, ask)
        elif not silent:
            self.root.after(0, lambda: messagebox.showinfo(
                self._h("Sin novedades", "No news", "Sem novidades"),
                self._h(f"Ya tenes la ultima version ({APP_VERSION}).",
                        f"You already have the latest version ({APP_VERSION}).",
                        f"Voce ja tem a ultima versao ({APP_VERSION}).")))

    def _show_update_banner(self, tag):
        """Aviso chico y no invasivo en el header — nunca un popup modal
        ni un cierre automatico. La persona lo ve, y si quiere, hace
        click cuando le convenga (nunca en medio de un stream sin que
        ella lo decida)."""
        self.update_banner_lbl.config(
            text=self._h(f"🔔 v{tag} disponible — click para instalar",
                         f"🔔 v{tag} available — click to install",
                         f"🔔 v{tag} disponivel — clique para instalar"))
        if not self.update_banner_lbl.winfo_ismapped():
            self.update_banner_lbl.pack(side="right", padx=(0, 16))

    def _confirm_install_update(self, _event=None):
        if not self._pending_update:
            return
        tag = self._pending_update["tag"]
        if messagebox.askyesno(
                self._h("Instalar actualizacion", "Install update", "Instalar atualizacao"),
                self._h(
                    f"Se va a instalar la version {tag}. MirrorDeck se va a cerrar "
                    "un momento y reabrir solo. ¿Continuar?",
                    f"Version {tag} is about to be installed. MirrorDeck will close "
                    "for a moment and reopen on its own. Continue?",
                    f"A versao {tag} vai ser instalada. O MirrorDeck vai fechar por "
                    "um instante e reabrir sozinho. Continuar?")):
            self._start_update_install()

    def _start_update_install(self):
        if not self._pending_update:
            return
        threading.Thread(
            target=self._download_update_bg,
            args=(self._pending_update["url"], self._pending_update["tag"], self._pending_update["notes"]),
            daemon=True).start()

    def _download_update_bg(self, url, tag="", notes=""):
        # Instalacion SILENCIOSA: la version anterior simplemente abria el
        # instalador con os.startfile(), que dispara el asistente completo
        # de Inno Setup (incluida la pantalla "La Carpeta Ya Existe" que
        # confunde a cualquiera que no sepa que es 100% normal y seguro
        # decirle que si). Para una actualizacion real de "un click" no
        # deberian aparecer esas pantallas: se corre con /VERYSILENT, que
        # usa las mismas rutas/opciones de la instalacion anterior sin
        # mostrar nada, salvo el UAC de administrador (inevitable en
        # Windows). Nuestro propio .exe esta bloqueado mientras corre, asi
        # que hay que cerrar MirrorDeck ANTES de que el instalador intente
        # sobreescribirlo — por eso el instalador se lanza con un pequeño
        # retraso (via cmd), desde un proceso aparte que sigue vivo
        # despues de que esta app se cierre.
        self._log(self._h("→ Descargando actualizacion...", "→ Downloading update...", "→ Baixando atualizacao..."))
        try:
            dest = Path(tempfile.gettempdir()) / "MirrorDeck_Setup_nuevo.exe"
            req = urllib.request.Request(url, headers={"User-Agent": "MirrorDeck"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
            self._log(self._h(f"✓ Actualizacion descargada: {dest}", f"✓ Update downloaded: {dest}", f"✓ Atualizacao baixada: {dest}"))

            # Guardamos las notas de esta version ANTES de cerrar, para
            # poder mostrarlas una sola vez cuando la app se reabra sola
            # (ver _maybe_show_changelog, llamado al arrancar).
            self.config["pending_changelog_version"] = tag
            self.config["pending_changelog_notes"] = notes
            self._save_config()

            cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            cf |= getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(
                f'cmd /c timeout /t 2 /nobreak >nul && '
                f'"{dest}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
                shell=True, creationflags=cf)

            self.root.after(0, lambda: (
                self._log(self._h(
                    "→ Cerrando MirrorDeck para aplicar la actualizacion...",
                    "→ Closing MirrorDeck to apply the update...",
                    "→ Fechando o MirrorDeck para aplicar a atualizacao...")),
                self.root.after(400, self.on_close)))
        except Exception as e:
            err_msg = str(e)  # ver nota en _activate_license_bg sobre por que capturamos esto antes del lambda diferido
            self._log(self._h(f"✗ Error descargando actualizacion: {err_msg}", f"✗ Error downloading update: {err_msg}", f"✗ Erro ao baixar a atualizacao: {err_msg}"))
            self.root.after(0, lambda: messagebox.showerror(
                "Error", self._h(f"No se pudo descargar la actualizacion:\n{err_msg}",
                                  f"Could not download the update:\n{err_msg}",
                                  f"Nao foi possivel baixar a atualizacao:\n{err_msg}")))

    # ── UTILS ────────────────────────────────────────────────────
    def _log(self, msg):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.root.after(0, _do)

    def _set_status(self, text, color=TEXT):
        self.status_var.set(text)
        self.status_hdr.config(fg=color)

    def on_close(self):
        self._stop_mirror()
        self._save_config()
        self.root.destroy()


def main():
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TCombobox",
                     fieldbackground=BG2, background=BG2, foreground=TEXT,
                     selectforeground=TEXT, selectbackground=ACCENT2,
                     arrowcolor=TEXT_DIM)
    style.map("TCombobox",
               fieldbackground=[("readonly", BG2)],
               foreground=[("readonly", TEXT)])
    app = MirrorDeckApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
