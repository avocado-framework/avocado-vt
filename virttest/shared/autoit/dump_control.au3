#cs ---------------------------------------------
AutoIt Version: 3.1.1.0
Author:Feng Yang

Script Function:
Handle BSOD dump file.
Now It can support 3 parameters.
This script will first install Windbg if not available.

parameter 1: Set the dump file link.
parameter 2: nfs link that used to save dump file.
parameter 3: symbols link used in windbg.
#ce ---------------------------------------------
Func InstallDBG($dbg)
    $para = "/package " & $dbg
    ShellExecute("msiexec", $para, "", "")
    WinWaitActive("[CLASS:MsiDialogCloseClass]")
    Send("{ENTER}")
    WinWaitActive("[CLASS:MsiDialogNoCloseClass]")
    ;ControlClick("[CLASS:MsiDialogNoCloseClass]", "End-User License Agreement", "[CLASS:Button, INSTANCE:2]")
    Send("!a")
    Send("!n")
    Send("!o")
    WinWaitActive("[CLASS:MsiDialogCloseClass]", "Ready to Instal")
    Send("!i")
    WinWaitActive("[CLASS:MsiDialogCloseClass]", "Click the Finish button to exit the Setup Wizard")
    Send("{ENTER}")
EndFunc

$time = @YEAR & "-" & @MON & "-" & @MDAY & "-" & @HOUR & "-" & @MIN & "-" & @SEC
$log_file = @OSVersion & $time & "_bsod.log"
if @OSArch = "X86" Then
    $file = "c:\Program Files\Debugging Tools for Windows (x86)\windbg.exe"
    $dbg = "D:\dbg_x86.msi"
ElseIf @OSArch = "X64" OR @OSArch = "IA64" Then
    $file = "c:\Program Files\Debugging Tools for Windows (x64)\windbg.exe"
    $dbg = "D:\dbg_amd64.msi"
EndIf
$nfs_link = "\\nfs_path"
$srv = "SRV*http://msdl.microsoft.com/download/symbols"
$dump_file = "C:\Windows\Memory.dmp"
Switch int($CmdLine[0])
    case 1
        $dump_file = $CmdLine[1]
    case 2
        $dump_file = $CmdLine[1]
        $nfs_link = $CmdLine[2]
    case 3
        $dump_file = $CmdLine[1]
        $nfs_link = $CmdLine[2]
        $srv = $CmdLine[3]
EndSwitch
$para = " -y " & $srv & " -z " & $dump_file

If FileExists($dump_file) Then
    if not FileExists($file) Then
        InstallDBG($dbg)
    EndIf
    ShellExecute($file, $para, "", "")
    $win_close = WinWaitActive("[CLASS:#32770]", "", 5)
    if $win_close <> 0 Then
        Send("!d")
        Send("!y")
    EndIf
    WinWaitActive("[CLASS:WinBaseClass]")
    sleep(2000)
    ControlSend("[CLASS:WinBaseClass]", "", "[CLASS:RichEdit20W; INSTANCE:2]", "{!}analyze -v {ENTER}")
    sleep(15000)

    $dump_text = ControlGetText("[CLASS:WinBaseClass]", "", "[CLASS:RichEdit20W; INSTANCE:1]")
    $file = FileOpen($log_file, 9)
    if $file == -1 Then
        ; Just try to open the file again.
        $file = FileOpen($log_file, 9)
    EndIf
    FileWrite($file, $dump_text)
    FileClose($file)
    WinClose("[CLASS:WinBaseClass]")
    WinClose("[CLASS:WinDbgFrameClass]")
    $win_close = WinWaitActive("[CLASS:#32770]", "", 10)
    if $win_close <> 0 Then
        Send("!d")
        Send("!y")
    EndIf
    $dest_dump_file = $nfs_link & @OSVersion & $time & ".dmp"
    $local_dump_file = "C:\Windows\" & $time & "-Memory.dmp"
    $s = FileCopy($dump_file, $dest_dump_file)
    if $s = 0 Then
        FileMove($dump_file, $local_dump_file)
    Else
        FileDelete($dump_file)
    EndIf
    $nfs_log_file = $nfs_link & $log_file
    $s = FileCopy($log_file, $nfs_log_file)
    if $s = 0 Then
        ; Just try again if file copy fail.
        FileCopy($log_file, $nfs_log_file)
    EndIf
    FileCopy($log_file, "C:\" & $log_file)
EndIf
Exit
