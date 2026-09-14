; ===========================================================================
; 호서대학교 정화민 - 연구실적 분석 포털 - Inno Setup 스크립트
;
; 빌드 방법:
;   1. python installer/windows/build_windows.py 실행
;   2. Inno Setup에서 이 파일을 열고 컴파일
;   3. dist/windows/ 에 설치 파일 생성
; ===========================================================================

#define MyAppName "호서대학교 정화민 - 연구실적 분석 포털"
#define MyAppVersion "5.0"
#define MyAppPublisher "정화민 (Junghwamin)"
#define MyAppExeName "launcher.pyw"

[Setup]
AppId={{E8F1A2B3-C4D5-6789-ABCD-EF0123456789}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\HoseoIRPortal
DefaultGroupName={#MyAppName}
OutputBaseFilename=HoseoIR_Setup_v{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
OutputDir=..\..\dist\windows
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; 빌드된 전체 앱 (Embedded Python + 앱 파일)
Source: "..\..\build\windows\HoseoIRPortal\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\output"
Name: "{app}\output\reports"
Name: "{app}\Raw data"

[Icons]
; 바탕화면 아이콘
Name: "{userdesktop}\연구실적 분석 포털"; \
    Filename: "{app}\python-embed\pythonw.exe"; \
    Parameters: """{app}\launcher.pyw"""; \
    WorkingDir: "{app}"; \
    IconFilename: "{app}\icon.ico"; \
    Comment: "호서대학교 정화민 - 연구실적 분석 포털"

; 시작 메뉴
Name: "{group}\연구실적 분석 포털"; \
    Filename: "{app}\python-embed\pythonw.exe"; \
    Parameters: """{app}\launcher.pyw"""; \
    WorkingDir: "{app}"; \
    IconFilename: "{app}\icon.ico"

Name: "{group}\언인스톨"; \
    Filename: "{uninstallexe}"

[Run]
; 설치 완료 후 바로 실행 옵션
Filename: "{app}\python-embed\pythonw.exe"; \
    Parameters: """{app}\launcher.pyw"""; \
    WorkingDir: "{app}"; \
    Description: "앱 바로 실행"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 런타임 생성 파일 정리
Type: filesandordirs; Name: "{app}\output"
Type: filesandordirs; Name: "{app}\Raw data"
Type: filesandordirs; Name: "{app}\.env"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\report_app\__pycache__"

[Code]
// 설치 완료 메시지 커스터마이징
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // output 및 Raw data 디렉토리 확인
    ForceDirectories(ExpandConstant('{app}\output\reports'));
    ForceDirectories(ExpandConstant('{app}\Raw data'));
  end;
end;
