; PrintLater installer (Inno Setup 6). Installs for the current user only, no administrator rights.
; Build: iscc /DAppVersion=1.2.0 packaging\installer.iss   (after PyInstaller has created dist\PrintLater)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{E1CBEF4A-3478-4781-9718-128BC402A55E}
AppName=PrintLater
AppVersion={#AppVersion}
AppVerName=PrintLater {#AppVersion}
AppPublisher=rgerr
AppPublisherURL=https://github.com/rgerr/printlater
AppSupportURL=https://github.com/rgerr/printlater/issues
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\PrintLater
DisableDirPage=yes
DefaultGroupName=PrintLater
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\PrintLater.exe
UninstallDisplayName=PrintLater
OutputDir=..\dist
OutputBaseFilename=PrintLater-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"

[CustomMessages]
en.SetToken=Set Home Assistant token
nl.SetToken=Home Assistant-token instellen
en.Check=Check settings
nl.Check=Instellingen controleren
en.EditConfig=Edit settings file
nl.EditConfig=Instellingenbestand bewerken
en.Queue=Print queue
nl.Queue=Printwachtrij
en.Next=Plan next job from the queue
nl.Next=Volgende uit de wachtrij inplannen

[InstallDelete]
; program files of an earlier install made with install.ps1 (settings and token are kept)
Type: filesandordirs; Name: "{localappdata}\PrintLater\app"

[Files]
Source: "..\dist\PrintLater\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config.example.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\homeassistant\printlater_delayed_start.yaml"; DestDir: "{app}\homeassistant"; Flags: ignoreversion
Source: "..\homeassistant\printlater_status_queue_example.yaml"; DestDir: "{app}\homeassistant"; Flags: ignoreversion
; settings live outside the program folder and survive updates and uninstall
Source: "..\config.example.toml"; DestDir: "{localappdata}\PrintLater"; DestName: "config.toml"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\PrintLater"; Filename: "{app}\PrintLater.exe"
Name: "{group}\{cm:SetToken}"; Filename: "{app}\PrintLater.exe"; Parameters: "set-token"
Name: "{group}\{cm:Check}"; Filename: "{app}\PrintLater.exe"; Parameters: "check"
Name: "{group}\{cm:Queue}"; Filename: "{app}\PrintLater.exe"; Parameters: "queue"
Name: "{group}\{cm:Next}"; Filename: "{app}\PrintLater.exe"; Parameters: "next"
Name: "{group}\{cm:EditConfig}"; Filename: "{win}\notepad.exe"; Parameters: """{localappdata}\PrintLater\config.toml"""

[Run]
Filename: "{app}\PrintLater.exe"; Parameters: "install-menu"; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\PrintLater.exe"; Parameters: "uninstall-menu"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveMenu"
