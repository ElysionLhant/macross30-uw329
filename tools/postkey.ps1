# 向 RPCS3 游戏窗口直接投递按键消息（不需要前台焦点）
# 用法: powershell -File postkey.ps1 -Key X          (按一下 Cross)
#       powershell -File postkey.ps1 -Key Return -Repeat 3 -DelayMs 1500
param(
  [string]$Key = "Return",
  [int]$Repeat = 1,
  [int]$HoldMs = 120,
  [int]$DelayMs = 500
)
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
public class Poster {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  public static IntPtr FindGameWindow() {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => {
      uint p = 0; GetWindowThreadProcessId(h, out p);
      try {
        var proc = System.Diagnostics.Process.GetProcessById((int)p);
        if (proc.ProcessName != "rpcs3") return true;
      } catch { return true; }
      if (!IsWindowVisible(h)) return true;
      var sb = new StringBuilder(256); GetWindowText(h, sb, 256);
      if (sb.ToString().Contains("BLJS10184")) { found = h; return false; }
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static IntPtr MakeLParam(int vk, bool up) {
    int scan = MapVirtualKey(vk, 0);
    int lp = 1 | (scan << 16);
    if (up) lp |= (1 << 30) | (1 << 31);
    return new IntPtr(lp);
  }
  [DllImport("user32.dll")] public static extern int MapVirtualKey(int vk, int mapType);
}
"@
$vkMap = @{ "Return"=0x0D; "Space"=0x20; "Left"=0x25; "Up"=0x26; "Right"=0x27; "Down"=0x28;
            "X"=0x58; "Z"=0x5A; "C"=0x43; "V"=0x56; "W"=0x57; "A"=0x41; "S"=0x53; "D"=0x44 }
$hwnd = [Poster]::FindGameWindow()
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "NO_WINDOW"; exit 1 }
$vk = $vkMap[$Key]
for ($i = 0; $i -lt $Repeat; $i++) {
  [void][Poster]::PostMessage($hwnd, 0x100, [IntPtr]$vk, [Poster]::MakeLParam($vk, $false))  # WM_KEYDOWN
  Start-Sleep -Milliseconds $HoldMs
  [void][Poster]::PostMessage($hwnd, 0x101, [IntPtr]$vk, [Poster]::MakeLParam($vk, $true))   # WM_KEYUP
  if ($i -lt $Repeat - 1) { Start-Sleep -Milliseconds $DelayMs }
}
Write-Output "POSTED $Key x$Repeat -> hwnd=$hwnd"
