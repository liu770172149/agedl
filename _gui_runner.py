# -*- coding: utf-8 -*-
import ctypes, os, subprocess, time
from ctypes import wintypes

CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
p = subprocess.Popen(['D:\\AGE下载器\\AGE下载器.exe'], cwd='D:\\AGE下载器', creationflags=CNW)
time.sleep(9)

user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
IsWindowVisible = user32.IsWindowVisible
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId

titles = []

def cb(hwnd, lparam):
    if not IsWindowVisible(hwnd):
        return True
    n = GetWindowTextLengthW(hwnd)
    if n == 0:
        return True
    buf = ctypes.create_unicode_buffer(n + 1)
    GetWindowTextW(hwnd, buf, n + 1)
    pid = wintypes.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == p.pid:
        titles.append((buf.value, pid.value, hwnd))
    return True

EnumWindows(EnumWindowsProc(cb), 0)
lines = [f"exe={D:\AGE下载器\AGE下载器.exe}", f"pid={p.pid}", f"alive={p.poll() is None}"]
for t, pid, hwnd in titles:
    lines.append(f"窗口: '{t}' pid={pid} hwnd={hwnd}")
if not titles:
    lines.append("没有找到可见窗口")
try:
    p.kill()
except Exception:
    pass
open('D:\\deepseekproject\\agedl\\_gui_result.txt', "w", encoding="utf-8").write("\n".join(lines))
