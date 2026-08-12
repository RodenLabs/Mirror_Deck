"""MirrorDeck - Instalador visual de dependencias"""
import tkinter as tk
from tkinter import ttk
import subprocess, threading, sys, winreg
import os, re, json, zipfile, tempfile, urllib.request
from pathlib import Path

BG="#1a1a2e"; BG2="#16213e"; BG3="#0f3460"; TEXT="#e0e0e0"; TEXT_DIM="#888888"
GREEN="#4ecca3"; RED="#e94560"; YELLOW="#f5c518"; BLUE="#4a9eff"
FONT=("Segoe UI",10); FONT_B=("Segoe UI",11,"bold"); FONT_S=("Segoe UI",9)

CONFIG_FILE = Path.home() / ".mirrordeck_config.json"

def get_windows_info():
    try:
        key=winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        build=int(winreg.QueryValueEx(key,"CurrentBuildNumber")[0])
        name=winreg.QueryValueEx(key,"ProductName")[0]
        winreg.CloseKey(key)
        return name,build,build>=22000
    except: return "Windows",0,False

def run_cmd(cmd,timeout=180):
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,shell=True,creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode,r.stdout.strip(),r.stderr.strip()
    except subprocess.TimeoutExpired: return -2,"","Tiempo agotado"
    except Exception as e: return -3,"",str(e)

def check_winget(): rc,out,_=run_cmd("winget --version"); return rc==0,out.strip()
def check_adb(): rc,out,_=run_cmd("adb version"); return rc==0,out.split("\n")[0] if out else ""
def check_scrcpy(): rc,out,_=run_cmd("scrcpy --version"); return rc==0,out.split("\n")[0] if out else ""

def install_winget():
    ps=("try{$url='https://aka.ms/getwinget';$tmp=\"$env:TEMP\\winget_setup.msixbundle\";"
        "Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing;"
        "Add-AppxPackage -Path $tmp -ErrorAction Stop;exit 0}catch{exit 1}")
    rc,_,_=run_cmd(f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{ps}"',timeout=240)
    return rc==0

def install_pkg(pkg_id):
    rc,out,err=run_cmd(f"winget install {pkg_id} --silent --accept-package-agreements --accept-source-agreements",timeout=240)
    return rc==0,(out or err or "sin detalle").strip()

# ── Descarga directa del zip portable oficial de scrcpy ──────────────
# El zip "scrcpy-win64-vX.Y.zip" que publica Genymobile en GitHub ya trae
# adentro scrcpy.exe + adb.exe + todas las DLL necesarias (SDL2, FFmpeg,
# AdbWinApi, etc.). No requiere instalador ni winget/App Installer, asi
# que funciona aunque la PC este recien formateada y winget este roto.
def _http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout)

def get_scrcpy_download_url():
    """Resuelve la ultima version publicada de scrcpy siguiendo el
    redirect de /releases/latest (no usa la API de GitHub, evita limites
    de rate y bloqueos de proxy)."""
    with _http_get("https://github.com/Genymobile/scrcpy/releases/latest", timeout=20) as resp:
        final_url = resp.geturl()
    m = re.search(r"/tag/v([\w.\-]+)", final_url)
    if not m:
        raise RuntimeError("No se pudo determinar la ultima version de scrcpy")
    version = m.group(1)
    url = f"https://github.com/Genymobile/scrcpy/releases/download/v{version}/scrcpy-win64-v{version}.zip"
    return url, version

def download_file(url, dest_path):
    with _http_get(url, timeout=60) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            f.write(chunk)

def install_scrcpy_portable(log_cb=None):
    """Descarga y extrae el zip portable oficial de scrcpy. Devuelve las
    rutas completas a scrcpy.exe y adb.exe ya extraidos."""
    target_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MirrorDeck" / "scrcpy"
    url, version = get_scrcpy_download_url()
    if log_cb: log_cb(f"  Descargando {url.rsplit('/',1)[-1]}...")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "scrcpy.zip"
        download_file(url, zip_path)
        if log_cb: log_cb("  Descarga completa. Extrayendo...")
        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target_dir)
    scrcpy_exe = next(target_dir.rglob("scrcpy.exe"), None)
    adb_exe    = next(target_dir.rglob("adb.exe"), None)
    if not scrcpy_exe or not adb_exe:
        raise RuntimeError("El zip descargado no contiene scrcpy.exe/adb.exe")
    return str(scrcpy_exe), str(adb_exe)

def save_paths_to_config(scrcpy_path=None, adb_path=None):
    """Escribe las rutas resueltas en el mismo archivo de config que lee
    android_mirror.py, para que la app las use sin que el usuario tenga
    que tocar nada."""
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
        except Exception:
            cfg = {}
    if scrcpy_path: cfg["scrcpy_path"] = scrcpy_path
    if adb_path:    cfg["adb_path"]    = adb_path
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

class InstallerApp:
    def __init__(self,root):
        self.root=root
        self.root.title("MirrorDeck - Configuracion")
        self.root.geometry("580x520"); self.root.resizable(False,False)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW",self._close)
        w=self.root.winfo_screenwidth(); h=self.root.winfo_screenheight()
        self.root.geometry(f"580x520+{(w-580)//2}+{(h-520)//2}")
        self._build(); self.root.after(400,self._start)

    def _build(self):
        hdr=tk.Frame(self.root,bg=BG3,pady=12); hdr.pack(fill="x")
        tk.Label(hdr,text="MirrorDeck",font=("Segoe UI",16,"bold"),bg=BG3,fg=TEXT).pack()
        self.win_label=tk.Label(hdr,text="Detectando sistema...",font=FONT_S,bg=BG3,fg=TEXT_DIM); self.win_label.pack()
        sf=tk.Frame(self.root,bg=BG,pady=8); sf.pack(fill="x",padx=20)
        self.steps={}
        for key,title in[("sistema","Sistema operativo"),("herramientas","ADB + scrcpy  (motor de espejo)")]:
            row=tk.Frame(sf,bg=BG,pady=5); row.pack(fill="x")
            ind=tk.Label(row,text="○",fg=TEXT_DIM,bg=BG,font=("Segoe UI",14),width=2); ind.pack(side="left")
            col=tk.Frame(row,bg=BG); col.pack(side="left",fill="x",expand=True,padx=(6,0))
            tk.Label(col,text=title,fg=TEXT,bg=BG,font=FONT_B,anchor="w").pack(fill="x")
            status=tk.Label(col,text="Esperando...",fg=TEXT_DIM,bg=BG,font=FONT_S,anchor="w",wraplength=440,justify="left"); status.pack(fill="x")
            self.steps[key]={"ind":ind,"status":status}
        tk.Label(self.root,text="",bg=BG).pack()
        self.bar=ttk.Progressbar(self.root,length=540,mode="indeterminate"); self.bar.pack(padx=20)
        lf=tk.Frame(self.root,bg=BG2); lf.pack(fill="both",expand=True,padx=20,pady=(10,8))
        self.log=tk.Text(lf,bg=BG2,fg=TEXT_DIM,font=("Consolas",8),relief="flat",state="disabled",wrap="word")
        sb=tk.Scrollbar(lf,command=self.log.yview); self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y"); self.log.pack(fill="both",expand=True,padx=4,pady=4)
        self.btn=tk.Button(self.root,text="Cerrar",command=self._close,bg=BG3,fg=TEXT_DIM,font=FONT,relief="flat",padx=24,pady=6,state="disabled",cursor="hand2"); self.btn.pack(pady=(0,10))

    def _step(self,key,state,msg):
        icons={"wait":("○",TEXT_DIM),"running":("◌",YELLOW),"ok":("✓",GREEN),"skip":("✓",BLUE),"error":("✗",RED)}
        colors={"wait":TEXT_DIM,"running":YELLOW,"ok":GREEN,"skip":BLUE,"error":RED}
        ic,ic_c=icons.get(state,("○",TEXT_DIM)); color=colors.get(state,TEXT_DIM)
        def _do(): self.steps[key]["ind"].config(text=ic,fg=ic_c); self.steps[key]["status"].config(text=msg,fg=color)
        self.root.after(0,_do)

    def _log(self,msg,color=None):
        def _do():
            self.log.config(state="normal"); idx=self.log.index("end-1c"); self.log.insert("end",msg+"\n")
            if color:
                tag=f"c{color[1:]}"; self.log.tag_configure(tag,foreground=color); self.log.tag_add(tag,idx,self.log.index("end-1c"))
            self.log.see("end"); self.log.config(state="disabled")
        self.root.after(0,_do)

    def _set_win_label(self,text,color=TEXT_DIM): self.root.after(0,lambda:self.win_label.config(text=text,fg=color))
    def _start(self): threading.Thread(target=self._run,daemon=True).start()

    def _run(self):
        self.root.after(0,self.bar.start)
        self._step("sistema","running","Detectando version de Windows...")
        win_name,build,is_win11=get_windows_info()
        if is_win11: win_str=f"Windows 11 (build {build})"; win_color=GREEN; step_msg=f"Windows 11 - build {build} - compatible"
        elif build>=17763: win_str=f"Windows 10 (build {build})"; win_color=BLUE; step_msg=f"Windows 10 - build {build} - compatible"
        else: win_str=f"Windows build {build}"; win_color=YELLOW; step_msg=f"Windows build {build}"
        self._set_win_label(win_str,win_color); self._step("sistema","ok",step_msg); self._log(f"Sistema: {win_str}",win_color)

        self._step("herramientas","running","Verificando ADB y scrcpy..."); self._log("\nVerificando ADB y scrcpy...")
        ok_adb,ver_adb=check_adb(); ok_sc,ver_sc=check_scrcpy()
        if ok_adb and ok_sc:
            self._step("herramientas","skip",f"Ya estan instalados.\nADB: {ver_adb}\nscrcpy: {ver_sc}")
            self._log(f"  ADB: {ver_adb}",GREEN); self._log(f"  scrcpy: {ver_sc}",GREEN)
            self._finish(True); return

        # Metodo principal: descargar el zip portable oficial de scrcpy.
        # Trae adb.exe adentro, asi que resuelve ambos con una sola descarga
        # y no depende de winget/App Installer (que puede fallar en una PC
        # recien formateada).
        self._step("herramientas","running","Descargando scrcpy portable (incluye ADB)...")
        self._log("\nADB y/o scrcpy no encontrados. Descargando paquete oficial portable de GitHub...")
        try:
            scrcpy_exe, adb_exe = install_scrcpy_portable(log_cb=lambda m: self._log(m))
            rc1,_,_ = run_cmd(f'"{adb_exe}" version')
            rc2,_,_ = run_cmd(f'"{scrcpy_exe}" --version')
            if rc1 != 0 or rc2 != 0:
                raise RuntimeError("los ejecutables descargados no respondieron")
            save_paths_to_config(scrcpy_path=scrcpy_exe, adb_path=adb_exe)
            self._step("herramientas","ok",f"Instalados (portable) en:\n{Path(scrcpy_exe).parent}")
            self._log(f"  OK. scrcpy y adb listos en {Path(scrcpy_exe).parent}",GREEN)
            self._finish(True); return
        except Exception as e:
            self._log(f"  Descarga directa fallo: {e}",YELLOW)
            self._log("  Probando con winget como alternativa...",YELLOW)

        # Fallback: winget (por si no hay salida a github pero si a winget,
        # o algun antivirus bloqueo la descarga directa).
        ok_wg,ver_wg=check_winget()
        if not ok_wg:
            self._log("  Instalando winget...",YELLOW)
            install_winget(); ok_wg,ver_wg=check_winget()
        if ok_wg:
            self._log(f"  winget: {ver_wg}",GREEN)
            if not ok_adb:
                self._log("  Instalando ADB via winget...")
                install_pkg("Google.AndroidPlatformTools")
            if not ok_sc:
                self._log("  Instalando scrcpy via winget...")
                install_pkg("Genymobile.scrcpy")
        else:
            self._log("  winget tampoco esta disponible.",RED)

        ok_f_adb,ver_f_adb=check_adb(); ok_f_sc,ver_f_sc=check_scrcpy()
        if ok_f_adb and ok_f_sc:
            self._step("herramientas","ok",f"Instalados via winget.\nADB: {ver_f_adb}\nscrcpy: {ver_f_sc}")
            self._log(f"  ADB: {ver_f_adb}",GREEN); self._log(f"  scrcpy: {ver_f_sc}",GREEN)
            self._finish(True)
        else:
            self._step("herramientas","error",
                "No se pudo instalar automaticamente.\n"
                "Descarga manual: github.com/Genymobile/scrcpy/releases/latest\n"
                "(extrae el zip win64 y anota la ruta de scrcpy.exe en la app)")
            self._log("  ERROR: no se pudo instalar ADB/scrcpy por ningun metodo.",RED)
            self._finish(False)

    def _finish(self,success):
        self.root.after(0,self.bar.stop)
        self._log("\n"+"="*50,TEXT_DIM)
        if success:
            self._log("Todo listo. MirrorDeck esta listo para usar.",GREEN)
            btn_text,btn_color="Cerrar",GREEN
        else:
            self._log("Algunos componentes no se instalaron.",RED); self._log("Lee los mensajes en rojo.",YELLOW)
            btn_text,btn_color="Cerrar (revisar errores)",YELLOW
        def _do():
            self.btn.config(state="normal",fg=btn_color,text=btn_text)
            # Esta ventana bloquea la continuacion del instalador principal
            # (Setup espera a que este proceso termine). Si salio todo bien
            # no tiene sentido que la persona tenga que hacer clic en algo
            # que no entiende: se cierra sola en unos segundos.
            if success:
                self.root.after(2500,self._close)
        self.root.after(0,_do)

    def _close(self): self.root.destroy(); sys.exit(0)

def main():
    root=tk.Tk(); style=ttk.Style(); style.theme_use("clam")
    style.configure("Horizontal.TProgressbar",troughcolor=BG2,background=GREEN)
    InstallerApp(root); root.mainloop()

if __name__=="__main__": main()
