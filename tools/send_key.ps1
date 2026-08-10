# 向 RPCS3 游戏窗口发送按键
# 用法: powershell -File send_key.ps1 -Key X          (按一下)
#       powershell -File send_key.ps1 -Key Return -HoldMs 200
param(
  [string]$Key = "Return",
  [int]$HoldMs = 120
)
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
public class KeySender {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] p, int cb);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public INPUTUNION u; }
  [StructLayout(LayoutKind.Explicit)] public struct INPUTUNION { [FieldOffset(0)] public KEYBDINPUT ki; }
  [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort vk; public ushort scan; public uint flags; public uint time; public IntPtr extra; }
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
  public static void Tap(ushort vk, int holdMs) {
    INPUT[] down = new INPUT[]{ new INPUT{ type=1, u=new INPUTUNION{ ki=new KEYBDINPUT{ vk=vk, flags=0 } } } };
    INPUT[] up   = new INPUT[]{ new INPUT{ type=1, u=new INPUTUNION{ ki=new KEYBDINPUT{ vk=vk, flags=2 } } } };
    SendInput(1, down, Marshal.SizeOf(typeof(INPUT)));
    Thread.Sleep(holdMs);
    SendInput(1, up, Marshal.SizeOf(typeof(INPUT)));
  }
}
"@
$vkMap = @{ "Return"=0x0D; "Space"=0x20; "Left"=0x25; "Up"=0x26; "Right"=0x27; "Down"=0x28;
            "X"=0x58; "Z"=0x5A; "C"=0x43; "V"=0x56; "W"=0x57; "A"=0x41; "S"=0x53; "D"=0x44 }
$hwnd = [KeySender]::FindGameWindow()
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "NO_WINDOW"; exit 1 }
[void][KeySender]::ShowWindow($hwnd, 9)  # SW_RESTORE
$fg = [KeySender]::SetForegroundWindow($hwnd)
Write-Output "hwnd=$hwnd fg=$fg"
Start-Sleep -Milliseconds 300
[KeySender]::Tap([uint16]$vkMap[$Key], $HoldMs)
Write-Output "SENT $Key"
