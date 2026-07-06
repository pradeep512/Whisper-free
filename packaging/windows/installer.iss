; Inno Setup script for Whisper-Free (issue #21).
;
; Wraps the PyInstaller onedir bundle (dist\Whisper-Free\, produced by
; packaging\windows\Whisper-Free.spec via scripts\build_windows.ps1) in a
; per-user installer: no admin rights, no UAC elevation prompt, installs to
; %LOCALAPPDATA%\Programs\Whisper-Free (mirrors PyInstaller's own onedir
; convention and keeps everything inside the current user's profile).
;
; Compile with:
;   iscc packaging\windows\installer.iss /DMyAppVersion=1.0.0
;
; scripts\build_windows.ps1 invokes this automatically after a successful
; PyInstaller build, passing the version it resolved from main_window.py.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

#define MyAppName "Whisper-Free"
#define MyAppExeName "Whisper-Free.exe"
#define MyAppPublisher "Whisper-Free"
#define BundleDir "..\..\dist\Whisper-Free"

[Setup]
AppId={{6F5A2A2E-6B1C-4A6D-9C9C-6E7C0D9E9B31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
; Per-user install: no admin rights, no UAC prompt.
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=Whisper-Free-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
; Unsigned, matching the macOS release posture -- SmartScreen friction accepted.
SignTool=
SetupIconFile=..\..\assets\app-icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "openatlogin"; Description: "Open Whisper-Free at login"; Flags: unchecked
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; "Open at login" writes the same HKCU Run value that
; app.platform.windows.autolaunch.set_open_at_login() writes/reads, so the
; Settings checkbox and the installer option stay consistent with each other.
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "Whisper-Free"; \
    ValueData: """{app}\{#MyAppExeName}"""; \
    Tasks: openatlogin; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
