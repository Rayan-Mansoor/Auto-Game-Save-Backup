; Inno Setup script: per-user install, no admin rights needed.
; Build after PyInstaller with: iscc /DAppVersion=0.1.0 packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6E0C6F7B-4D7E-4C59-9B67-5A8F2B1D3C21}
AppName=SaveIX
AppVersion={#AppVersion}
AppPublisher=SaveIX
DefaultDirName={localappdata}\Programs\saveix
DefaultGroupName=SaveIX
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=saveix-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\saveix-tray.exe

[Tasks]
Name: "autostart"; Description: "Start SaveIX when I log in to Windows"; GroupDescription: "Background backups:"
Name: "addtopath"; Description: "Add the saveix command to my PATH"; GroupDescription: "Command line:"; Flags: unchecked

[Files]
Source: "..\dist\saveix\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SaveIX"; Filename: "{app}\saveix-tray.exe"
Name: "{group}\Uninstall SaveIX"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "saveix"; ValueData: """{app}\saveix-tray.exe"""; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\saveix-tray.exe"; Description: "Start SaveIX now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM saveix-tray.exe /F"; Flags: runhidden; RunOnceId: "StopTray"

[Code]
function NeedsAddPath(Folder: string): Boolean;
var
  Paths: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Folder) + ';', ';' + Uppercase(Paths) + ';') = 0;
end;
