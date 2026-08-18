!ifndef VERSION
  !define VERSION "0.0.0"
!endif

!include "MUI2.nsh"
!define MUI_FINISHPAGE_RUN "$INSTDIR\ADB-Explorer.exe"

Name "ADB Explorer"
OutFile "..\..\dist\ADB-Explorer-${VERSION}-setup.exe"
InstallDir "$PROGRAMFILES64\ADB Explorer"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetShellVarContext all
  SetOutPath "$INSTDIR"
  File "..\..\dist\ADB-Explorer.exe"
  File /nonfatal "..\..\assets\logo.svg"
  CreateDirectory "$SMPROGRAMS\ADB Explorer"
  CreateShortcut "$DESKTOP\ADB Explorer.lnk" "$INSTDIR\ADB-Explorer.exe"
  CreateShortcut "$SMPROGRAMS\ADB Explorer\ADB Explorer.lnk" "$INSTDIR\ADB-Explorer.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\ADB Explorer\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  SetShellVarContext all
  Delete "$DESKTOP\ADB Explorer.lnk"
  Delete "$SMPROGRAMS\ADB Explorer\ADB Explorer.lnk"
  Delete "$SMPROGRAMS\ADB Explorer\Uninstall.lnk"
  RMDir "$SMPROGRAMS\ADB Explorer"
  Delete "$INSTDIR\ADB-Explorer.exe"
  Delete "$INSTDIR\logo.svg"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
