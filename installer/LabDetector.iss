#define MyAppId "{{A48DB687-BD0A-4F91-B7B3-6AFB0C2DCE41}}"
#define MyAppName "LabDetector"
#define MyAppDisplayName "LabDetector Intelligent Laboratory Desktop Suite"
#define MyAppPublisher "LabDetector Software Team"
#define MyAppURL "https://github.com/xiao2003/Labdetector"
#define MyAppExeName "LabDetector.exe"
#define MyPanelExeName "LabDetectorPanel.exe"
#define MyTrainingExeName "LabDetectorTraining.exe"
#define MyAliasExeName "Lab.exe"
#define MyAliasPanelExeName "LabPanel.exe"
#define MyAliasTrainingExeName "LabTraining.exe"
#ifndef MyAppVersion
  #define MyAppVersion "3.0.2"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\\pc"
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
AppCopyright=Copyright (C) 2026 LabDetector Software Team. All rights reserved.
DefaultDirName={autopf}\LabDetector
DefaultGroupName=LabDetector
DisableProgramGroupPage=yes
DisableDirPage=no
LicenseFile=LICENSE_zh_cn.txt
InfoBeforeFile=INFO_zh_cn.txt
WizardStyle=modern
SetupIconFile=..\assets\branding\labdetector.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
OutputDir=..
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
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional tasks"

[Dirs]
Name: "{app}\APP"; Attribs: hidden system

[Files]
Source: "{#ReleaseDir}\LabDetector.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\LabDetectorPanel.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\LabDetectorTraining.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\Lab.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\LabPanel.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\LabTraining.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\APP\*"; DestDir: "{app}\APP"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\LabDetector"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\LabDetector 控制面板"; Filename: "{app}\{#MyPanelExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyPanelExeName}"
Name: "{autoprograms}\LabDetector 训练工作台"; Filename: "{app}\{#MyTrainingExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyTrainingExeName}"
Name: "{autodesktop}\LabDetector"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch LabDetector now"; Flags: nowait postinstall skipifsilent
