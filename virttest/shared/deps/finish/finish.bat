taskkill /IM serialport.exe /F

if [%~3]==[-AccomplishWinUpdates] (
    set has_update=1
) else (
    set has_update=0
)

:check_net
if [%~2]==[] goto check_process

set ping_host=%~2
echo Check network status > COM1
ping %ping_host%

if errorlevel 1 goto check_net

:check_process
if [%~1]==[] goto end

set process=%~1
echo Check %process% status >  COM1
tasklist /FO List>  C:\log
type C:\log|find "%process%"

if errorlevel 1 goto end
if errorlevel 0 goto check_process

:end
reg add "HKLM\System\CurrentControlSet\Control\CrashControl" /v AutoReboot /d 0 /t REG_DWORD /f
reg add "HKLM\System\CurrentControlSet\Control\CrashControl" /v CrashDumpEnabled /d 2 /t REG_DWORD /f
reg add "HKLM\System\CurrentControlSet\Control\CrashControl" /v NMICrashDump  /d 1 /t REG_DWORD /f
reg add "HKLM\System\CurrentControlSet\Control\CrashControl" /v DumpFile /d %SystemRoot%\Memory.dmp /t REG_EXPAND_SZ /f
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v bsod /d "D:\autoit3.exe D:\dump_control.au3" /t REG_SZ /f
reg add "HKLM\System\CurrentControlSet\Control\CrashControl" /v AlwaysKeepMemoryDump /d 1 /t REG_DWORD /f
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\Windows Error Reporting" /v Disabled /d 1 /t REG_DWORD /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\vds" /v Start /t REG_DWORD /d 3 /f

if [%has_update%]==[1] (
    reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce" /v PostSetupEvent /d "cmd /c """for %%i in ^(1,1,5^) do ^(echo Post set up finished^> COM1^)"" /t REG_SZ /f
    shutdown /r /f /t 0
) else (
    for /L %%i in (1,1,3) do (echo Post set up finished> COM1)
)
