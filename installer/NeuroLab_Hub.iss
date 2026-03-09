#define MyAppId "{{A48DB687-BD0A-4F91-B7B3-6AFB0C2DCE41}}"
#define MyAppName "NeuroLab Hub"
#define MyAppDisplayName "NeuroLab Hub——可编排专家模型的实验室多模态智能中枢"
#define MyAppPublisher "NeuroLab Hub Software Team"
#define MyAppURL "https://github.com/xiao2003/Labdetector"
#define MyAppExeName "NeuroLab Hub.exe"
#define MyLlmExeName "NeuroLab Hub LLM.exe"
#define MyVisionExeName "NeuroLab Hub Vision.exe"
#ifndef MyAppVersion
  #define MyAppVersion "3.0.7"
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
AppCopyright=Copyright (C) 2026 NeuroLab Hub Software Team. All rights reserved.
DefaultDirName={autopf}\NeuroLab Hub
DefaultGroupName=NeuroLab Hub
DisableProgramGroupPage=yes
DisableDirPage=no
LicenseFile=LICENSE_zh_cn.txt
InfoBeforeFile=INFO_zh_cn.txt
WizardStyle=modern
SetupIconFile=..\assets\branding\neurolab_hub.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
OutputDir=..
OutputBaseFilename=NeuroLab-Hub-Setup-v{#MyAppVersion}
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
Source: "{#ReleaseDir}\NeuroLab Hub.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\NeuroLab Hub LLM.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\NeuroLab Hub Vision.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\APP\*"; DestDir: "{app}\APP"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\NeuroLab Hub"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\NeuroLab Hub LLM 微调"; Filename: "{app}\{#MyLlmExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyLlmExeName}"
Name: "{autoprograms}\NeuroLab Hub Vision 训练"; Filename: "{app}\{#MyVisionExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyVisionExeName}"
Name: "{autodesktop}\NeuroLab Hub"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NeuroLab Hub now"; Flags: nowait postinstall skipifsilent
