# Start a game, wait, capture its own window (whatever is in front of it), end it.
# gameshot.ps1 -Exe <game exe> -Out <png> [-Wait 20] [-WorkDir <dir>]
param([string]$Exe, [string]$Out, [int]$Wait = 20, [string]$WorkDir = "")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class ViwoShot {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
"@
$dir = Split-Path -Parent $Exe
if (-not $WorkDir) { $WorkDir = $dir }
$game = Start-Process -FilePath $Exe -WorkingDirectory $WorkDir -PassThru
$deadline = (Get-Date).AddSeconds(90); $win = $null
while ((Get-Date) -lt $deadline -and -not $win) {
    Start-Sleep -Milliseconds 500
    $win = Get-Process | Where-Object { $_.Path -like "$dir\*" -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
}
if (-not $win) { "no window from $Exe"; Get-Process | Where-Object { $_.Path -like "$dir\*" } | Stop-Process -Force; exit 1 }
Start-Sleep -Seconds $Wait
$win.Refresh(); $h = $win.MainWindowHandle
[ViwoShot]::ShowWindow($h, 9) | Out-Null; [ViwoShot]::SetForegroundWindow($h) | Out-Null; Start-Sleep -Seconds 2
$r = New-Object ViwoShot+RECT; [ViwoShot]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ([Math]::Max(1, $r.R - $r.L)), ([Math]::Max(1, $r.B - $r.T))
$g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
$ok = [ViwoShot]::PrintWindow($h, $dc, 2); $g.ReleaseHdc($dc); $g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
"window '$($win.MainWindowTitle)' $($r.R - $r.L)x$($r.B - $r.T) printed=$ok"
Get-Process | Where-Object { $_.Path -like "$dir\*" } | Stop-Process -Force
