; Instalador Bridge CMYK (Inno Setup 6)
; Compilar com: ISCC.exe bridgecmyk_setup.iss

#define AppName "Bridge CMYK"
#define AppVersion "0.1.0"
#define AppExe "BridgeCMYK.exe"

[Setup]
AppId={{B5DCA85A-F2E4-4DC4-A42B-8C8C3A477C0E}
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
