@echo off
title Construyendo MirrorDeck v4...

echo.
echo === MirrorDeck v4 - Construir instalador ===
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado.
    pause & exit /b 1
)
echo [OK] Python encontrado.

pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [..] Instalando PyInstaller...
    pip install pyinstaller -q
)
echo [OK] PyInstaller listo.

if exist icon.ico (
    echo [OK] icon.ico de MirrorDeck ya presente, se usa ese.
) else (
    echo [..] Generando icono basico de respaldo...
    python generate_icon.py
    echo [OK] Icono generado.
)

echo.
echo [..] Compilando MirrorDeck.exe (2-3 min)...
REM --noupx: los antivirus (Malwarebytes, Defender, etc.) marcan como
REM sospechosos los .exe comprimidos con UPX con muchisima frecuencia,
REM porque el malware tambien usa UPX para esconder su contenido del
REM analisis estatico. Sin UPX el .exe pesa un poco mas, pero baja
REM mucho el riesgo de falso positivo "Malware.AI.xxxxx".
REM --onedir (en vez de --onefile): un .exe de un solo archivo se
REM auto-extrae a una carpeta temporal CADA VEZ que arranca; si un
REM antivirus interfiere justo en ese instante (muy probable en un
REM build recien compilado, que todavia no esta "conocido" por el AV),
REM la extraccion queda a medias y la app explota con "Failed to load
REM Python DLL". Con --onedir los archivos ya estan extraidos de
REM antemano en la carpeta de instalacion, sin extraccion en cada
REM inicio, lo que elimina esa ventana de riesgo por completo.
pyinstaller --onedir --windowed --noupx --name "MirrorDeck" ^
  --icon "icon.ico" ^
  --add-data "icon.ico;." ^
  --add-data "icon_40.png;." ^
  --manifest "android_mirror.manifest" ^
  android_mirror.py --clean -y >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Fallo al compilar MirrorDeck.exe
    pause & exit /b 1
)
echo [OK] MirrorDeck.exe compilado.

if exist icon.ico (
    copy /Y icon.ico dist\icon.ico >nul 2>&1
)

echo [..] Compilando InstalarDependencias.exe...
pyinstaller --onedir --windowed --noupx --name "InstalarDependencias" ^
  --icon "icon.ico" ^
  --manifest "install_gui.manifest" ^
  install_gui.py --clean -y >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Fallo al compilar InstalarDependencias.exe
    pause & exit /b 1
)
echo [OK] InstalarDependencias.exe compilado.

if exist tap_mapper.apk (
    echo [OK] tap_mapper.apk encontrado - se va a incluir en el instalador.
) else (
    echo [INFO] tap_mapper.apk no encontrado - el instalador se genera igual,
    echo        pero el boton "Instalar Tap Mapper" no va a tener que instalar.
)

set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set ISCC="%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo [ERROR] Inno Setup 6 no encontrado.
    pause & exit /b 1
)
echo [OK] Inno Setup encontrado.

echo [..] Generando instalador final...
%ISCC% installer.iss
if %errorlevel% neq 0 (
    echo [ERROR] Fallo al generar el instalador.
    pause & exit /b 1
)

echo.
echo =====================================================
echo  LISTO.
echo  MirrorDeck_Distribuir\MirrorDeck_Setup.exe
echo  Ese archivo es todo lo que necesita tu tester.
echo =====================================================
echo.
pause
