set rsspath=%1
if [%1]==[] set rsspath=%~dp0\rss6.exe
copy %rsspath% C:\rss6.exe

net user Administrator /active:yes
net user Administrator 1q2w3eP
netsh firewall set opmode disable
netsh advfirewall set allprofiles state off
netsh interface ipv6 set global randomizeidentifiers=disabled
powercfg /G OFF /OPTION RESUMEPASSWORD

reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v "Remote Shell Server IPv6" /d "C:\rss6.exe" /t REG_SZ /f
reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion\winlogon" /v "AutoAdminLogon" /d "1" /t REG_SZ /f
reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion\winlogon" /v "DefaultUserName" /d "Administrator" /t REG_SZ /f
reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion\winlogon" /v "DefaultPassword" /d "1q2w3eP" /t REG_SZ /f
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v "EnableLUA" /d "0" /t REG_DWORD /f
reg add "HKLM\Software\Policies\Microsoft\Windows NT\Reliability" /v "ShutdownReasonOn" /d "0" /t REG_DWORD /f

rem Just in case reg6.exe is missing (e.g. Windows 2000):
regedit /s %~dp0\rss6.reg

start /B C:\rss6.exe
