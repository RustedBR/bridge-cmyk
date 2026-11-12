; Instalador Bridge CMYK (Inno Setup 6)
; Compilar com: ISCC.exe bridgecmyk_setup.iss

#define AppName "Bridge CMYK"
#define AppVersion "0.1.0"
#define AppExe "BridgeCMYK.exe"

[Setup]
AppId={{8F2C6A1E-3D77-4B1E-9E54-BRIDGE-CMYK01}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\BridgeCMYK
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=BridgeCMYKSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist
Source: "..\LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Bridge CMYK"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Bridge CMYK"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o Bridge CMYK agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
