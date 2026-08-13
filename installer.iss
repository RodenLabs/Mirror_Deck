#define AppName "MirrorDeck"
#define AppVersion "4.2.6"
#define AppExeName "MirrorDeck.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Roden Labs
AppPublisherURL=https://mirrordeck.netlify.app
DefaultDirName={autopf}\MirrorDeck
DefaultGroupName={#AppName}
; Instalador nativo de 64 bits: hoy practicamente ninguna PC corre Windows
; de 32 bits, asi que no hace falta mantener 2 versiones. Sin esto, Inno
; Setup instala por default en modo 32 bits (carpeta "Program Files (x86)").
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; El AppId es el mismo de la version vieja "Android Mirror" (para que Inno
; Setup lo reconozca como una actualizacion y no como un programa nuevo
; separado), pero forzamos que use la carpeta/grupo NUEVOS en vez de
; reusar la ruta vieja "...\AndroidMirror" que Inno guarda en el registro.
UsePreviousAppDir=no
UsePreviousGroup=no
OutputDir=..\MirrorDeck_Distribuir
OutputBaseFilename=MirrorDeck_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
SetupIconFile=dist\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"
Name: "startmenu";   Description: "Agregar al Menu Inicio"

[Files]
Source: "dist\MirrorDeck.exe";           DestDir: "{app}"; Flags: ignoreversion
Source: "dist\InstalarDependencias.exe"; DestDir: "{app}"; Flags: ignoreversion
; Opcional: si existe tap_mapper.apk junto a este script, se incluye en el
; instalador y MirrorDeck puede instalarlo en el celular con un boton.
; Si no existe, ISCC compila igual (skipifsourcedoesntexist) y ese boton
; simplemente avisa que falta el archivo.
Source: "tap_mapper.apk"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{commondesktop}\MirrorDeck";     Filename: "{app}\MirrorDeck.exe"; Tasks: desktopicon
Name: "{group}\MirrorDeck";             Filename: "{app}\MirrorDeck.exe"; Tasks: startmenu
Name: "{group}\Desinstalar MirrorDeck"; Filename: "{uninstallexe}"

[Run]
; Sin "postinstall": se ejecuta solo, sin checkbox que se pueda desmarcar,
; y Setup ESPERA a que termine (sin "nowait") antes de mostrar la pantalla
; final. Asi queda garantizado que ADB y scrcpy estan listos antes de que
; la persona pueda abrir MirrorDeck.
Filename: "{app}\InstalarDependencias.exe"; \
    StatusMsg: "Instalando ADB y scrcpy..."; \
    Flags: waituntilterminated

; Sin "skipifsilent": cuando el auto-updater de la app corre este
; instalador con /VERYSILENT, este paso SI tiene que ejecutarse para que
; MirrorDeck se reabra solo con la version nueva (si tuviera skipifsilent,
; una actualizacion silenciosa dejaria la app cerrada sin avisar).
Filename: "{app}\MirrorDeck.exe"; \
    Description: "Abrir MirrorDeck ahora"; \
    Flags: nowait postinstall

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
