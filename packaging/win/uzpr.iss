[Setup]
AppName=Ultimate ZIP Password Recover
AppVersion=0.1.0
AppPublisher=Luis Fialho
AppPublisherURL=https://github.com/LuisPCFialho/ultimate-zip-password-recover
DefaultDirName={autopf}\UltimateZipPasswordRecover
DefaultGroupName=Ultimate ZIP Password Recover
AllowNoIcons=yes
OutputDir=packaging\win\output
OutputBaseFilename=UltimateZipPasswordRecover-Setup-x64
SetupIconFile=packaging\win\uzpr.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\UltimateZipPasswordRecover\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Ultimate ZIP Password Recover"; Filename: "{app}\UltimateZipPasswordRecover.exe"
Name: "{group}\{cm:UninstallProgram,Ultimate ZIP Password Recover}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Ultimate ZIP Password Recover"; Filename: "{app}\UltimateZipPasswordRecover.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\UltimateZipPasswordRecover.exe"; Description: "{cm:LaunchProgram,Ultimate ZIP Password Recover}"; Flags: nowait postinstall skipifsilent
