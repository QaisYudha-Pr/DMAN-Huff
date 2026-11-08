@echo off
echo [*] Registering PyIDM protocol handler (pyidm://)...
set "KEY=HKCU\Software\Classes\pyidm"
reg add "%KEY%" /ve /t REG_SZ /d "URL:PyIDM Protocol" /f >nul
reg add "%KEY%" /v "URL Protocol" /t REG_SZ /d "" /f >nul
reg add "%KEY%\shell\open\command" /ve /t REG_SZ /d "pythonw \"c:\Users\asus\Downloads\11-12-IDM\idm_gui.py\" \"%%1\"" /f >nul
echo [+] Successfully registered pyidm:// protocol in Windows!
pause

