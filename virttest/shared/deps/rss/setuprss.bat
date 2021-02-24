rem Enable delayed expansion to be able to use !ERRORLEVEL!
setlocal enabledelayedexpansion
set rsspath=%1

if [%1]==[] (
    echo "Guessing rss path to use based on processor architecture"
    :: Not using the PROCESSOR_ARCHITECTURE environment variable directly here as there are situations in Win7
    :: install where the installation will be x64 but the environment variables, and the file system at
    :: that point, are in a 32-bit state and %PROCESSOR_ARCHITECTURE% will return x86 on AMD64 hardware.
    :: Since this file is called during the unattended installation, it is best to access the variable from
    :: the registry instead. More information: https://github.com/avocado-framework/avocado-vt/pull/2920#discussion_r579332634
    reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PROCESSOR_ARCHITECTURE | find /i "x86" > nul
    if !ERRORLEVEL!==0 (
        echo "Windows 32-bits detected"
        set rsspath=%~dp0\rss.exe
    ) else (
        echo "Windows 64-bits detected"
        set rsspath=%~dp0\rss_amd64.exe
    )
)
copy %rsspath% C:\rss.exe

net user Administrator /active:yes
net user Administrator 1q2w3eP
netsh firewall set opmode disable
netsh advfirewall set allprofiles state off
powercfg /G OFF /OPTION RESUMEPASSWORD

reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v "Remote Shell Server" /d "C:\rss.exe" /t REG_SZ /f
reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion\winlogon" /v "AutoAdminLogon" /d "1" /t REG_SZ /f
reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion\winlogon" /v "DefaultUserName" /d "Administrator" /t REG_SZ /f
reg add "HKLM\Software\Microsoft\Windows NT\CurrentVersion\winlogon" /v "DefaultPassword" /d "1q2w3eP" /t REG_SZ /f
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v "EnableLUA" /d "0" /t REG_DWORD /f
reg add "HKLM\Software\Policies\Microsoft\Windows NT\Reliability" /v "ShutdownReasonOn" /d "0" /t REG_DWORD /f

rem Just in case reg.exe is missing (e.g. Windows 2000):
regedit /s %~dp0\rss.reg

start /B C:\rss.exe
