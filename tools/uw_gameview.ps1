param([string]$Out = "gameview.png")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W32 {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$found = [IntPtr]::Zero
$cb = {
  param($hwnd, $l)
  $procId = 0
  [W32]::GetWindowThreadProcessId($hwnd, [ref]$procId) | Out-Null
  try { $pn = (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { return $true }
  if ($pn -ne 'rpcs3') { return $true }
  if (-not [W32]::IsWindowVisible($hwnd)) { return $true }
  $sb = New-Object System.Text.StringBuilder 256
  [W32]::GetWindowText($hwnd, $sb, 256) | Out-Null
  if ($sb.ToString() -match 'BLJS10184') { $script:found = $hwnd; return $false }
  return $true
}
[W32]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
if ($found -eq [IntPtr]::Zero) { Write-Output "NO_GAME_WINDOW"; exit 1 }
[void][W32]::SetForegroundWindow($found)
Start-Sleep -Milliseconds 600
$r = New-Object W32+RECT
[W32]::GetWindowRect($found, [ref]$r) | Out-Null
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "saved $Out ${w}x${h}"
