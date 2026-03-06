#define MyAppId "{{A48DB687-BD0A-4F91-B7B3-6AFB0C2DCE41}}"
#define MyAppName "LabDetector"
#define MyAppDisplayName "LabDetector 智能实验室监控软件"
#define MyAppPublisher "LabDetector 软件研发组"
#define MyAppURL "https://github.com/xiao2003/Labdetector"
#define MyAppExeName "LabDetector.exe"
#ifndef MyAppVersion
  #define MyAppVersion "3.0.1"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\\release\\LabDetector-v" + MyAppVersion
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} V{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright (C) 2026 LabDetector 软件研发组. All rights reserved.
DefaultDirName={autopf}\LabDetector
DefaultGroupName=LabDetector
DisableProgramGroupPage=yes
LicenseFile={#ReleaseDir}\_internal\docs\软件版权声明.md
InfoBeforeFile={#ReleaseDir}\_internal\docs\LabDetector软件说明书.md
WizardStyle=modern
SetupIconFile=..\assets\branding\labdetector.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
OutputDir=..\release
OutputBaseFilename=LabDetector-Setup-v{#MyAppVersion}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
MinVersion=10.0
UsePreviousAppDir=yes
UsePreviousTasks=yes
UsePreviousLanguage=yes
ChangesEnvironment=no
CloseApplications=yes
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务"

[Dirs]
Name: "{app}\_internal"; Attribs: hidden system

[Files]
Source: "{#ReleaseDir}\LabDetector.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\LabDetector"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\LabDetector"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "安装完成后立即启动 LabDetector"; Flags: nowait postinstall skipifsilent
