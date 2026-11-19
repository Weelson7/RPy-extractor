# Start a game, wait, capture its own window (whatever is in front of it), end it.
# game_shot.ps1 -Exe <game exe> -Out <png> [-Wait 20] [-WorkDir <dir>] [-Keys "{ENTER}"]
# -Keys: keystrokes sent to the game's window before the capture (SendKeys syntax, e.g. to
# dismiss a start-up dialog or skip a movie); several separated by | ("{ESC}|{ESC}"), each
# followed by -KeyWait seconds. The window is looked up again for up to 30 s after them.
# -Screen: copy the window's area from the screen instead of printing the window (a game drawing
# full screen through DirectX prints black).
param([string]$Exe, [string]$Out, [int]$Wait = 20, [string]$WorkDir = "", [string[]]$Keys = @(),
      [int]$KeyWait = 5, [switch]$Screen)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class ViwoShot {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
"@
[ViwoShot]::SetProcessDPIAware() | Out-Null  # real pixels: a scaled display cut the window short
$dir = Split-Path -Parent $Exe
if (-not $WorkDir) { $WorkDir = $dir }
$game = Start-Process -FilePath $Exe -WorkingDirectory $WorkDir -PassThru
# the window is looked up afresh each time: a game may swap its window while it starts
function Find-GameWindow {
    Get-Process | Where-Object { $_.Path -like "$dir\*" -and $_.MainWindowHandle -ne 0 } |
        Select-Object -First 1
}
function Stop-Game { Get-Process | Where-Object { $_.Path -like "$dir\*" } | Stop-Process -Force }
$deadline = (Get-Date).AddSeconds(90); $win = $null
while ((Get-Date) -lt $deadline -and -not $win) {
    Start-Sleep -Milliseconds 500
    $win = Find-GameWindow
}
if (-not $win) { "no window from $Exe"; Get-Process | Where-Object { $_.Path -like "$dir\*" } | Stop-Process -Force; exit 1 }
Start-Sleep -Seconds $Wait
$win = Find-GameWindow
if (-not $win) { "the window of $Exe closed while waiting"; Stop-Game; exit 1 }
$h = $win.MainWindowHandle
[ViwoShot]::ShowWindow($h, 9) | Out-Null; [ViwoShot]::SetForegroundWindow($h) | Out-Null; Start-Sleep -Seconds 2
foreach ($key in ($Keys -join '|') -split '\|' | Where-Object { $_ }) {
    [ViwoShot]::SetForegroundWindow($h) | Out-Null
    (New-Object -ComObject WScript.Shell).SendKeys($key); "sent $key"; Start-Sleep -Seconds $KeyWait
}
if ($Keys) {
    $until = (Get-Date).AddSeconds(30); $win = Find-GameWindow
    while (-not $win -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 500; $win = Find-GameWindow }
    if (-not $win) { "the window closed after the keys"; Stop-Game; exit 1 }
    $h = $win.MainWindowHandle
}
$r = New-Object ViwoShot+RECT; [ViwoShot]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ([Math]::Max(1, $r.R - $r.L)), ([Math]::Max(1, $r.B - $r.T))
$g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
if ($Screen) {
    $g.ReleaseHdc($dc); $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size); $ok = "screen"
} else { $ok = [ViwoShot]::PrintWindow($h, $dc, 2); $g.ReleaseHdc($dc) }
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
"window '$($win.MainWindowTitle)' $($r.R - $r.L)x$($r.B - $r.T) printed=$ok"
Get-Process | Where-Object { $_.Path -like "$dir\*" } | Stop-Process -Force
