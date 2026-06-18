; Inno Setup script for DariaTech Data Cleanup
; Builds a real Windows installer with Start Menu + Desktop shortcuts and an uninstaller.

#define MyAppName "DariaTech Data Cleanup"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DariaTech IT-Systemhaus"
#define MyAppURL "https://www.dariatech.de"
#define MyAppExeName "DariaTech-Data-Cleanup.exe"

[Setup]
; Unique application id (keep stable across versions for clean upgrades).
AppId={{8F3C2A1B-4D5E-4F6A-9B2C-1D7E8F9A0B3C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\DariaTech Data Cleanup
DefaultGroupName=DariaTech Data Cleanup
DisableProgramGroupPage=yes
; Resolve all relative paths from the repository root (one level above this script).
SourceDir={#SourcePath}\..
OutputDir=installer_output
OutputBaseFilename=DariaTech-Data-Cleanup-Setup
SetupIconFile=web\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\DariaTech-Data-Cleanup.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\DariaTech Data Cleanup"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,DariaTech Data Cleanup}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\DariaTech Data Cleanup"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,DariaTech Data Cleanup}"; Flags: nowait postinstall skipifsilent
