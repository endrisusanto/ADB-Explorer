!ifndef VERSION
  !define VERSION "0.0.0"
!endif

Name "ADB Explorer"
OutFile "dist\ADB-Explorer-${VERSION}-setup.exe"
InstallDir "$PROGRAMFILES64\ADB Explorer"
RequestExecutionLevel admin

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File "dist\ADB Explorer.exe"
  File /nonfatal "assets\logo.svg"
  CreateShortcut "$DESKTOP\ADB Explorer.lnk" "$INSTDIR\ADB Explorer.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\ADB Explorer.lnk"
  Delete "$INSTDIR\ADB Explorer.exe"
  Delete "$INSTDIR\logo.svg"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
