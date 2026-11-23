# -*- coding: utf-8 -*-
"""直接启动 GUI 并枚举所有可见顶层窗口，找到下载器窗口即视为通过。"""
import ctypes
import io
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

APP = r"D:\AGE下载器"
EXE = os.path.join(APP, "AGE下载器.exe")

user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
IsWindowVisible = user32.IsWindowVisible
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId


def windows_of(pids):
    found = []

    def cb(hwnd, _lp):
        if not IsWindowVisible(hwnd):
            return True
        n = GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        GetWindowTextW(hwnd, buf, n + 1)
        pid = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            found.append((buf.value, pid.value, hwnd))
        return True

    EnumWindows(EnumWindowsProc(cb), 0)
    return found


print("exe:", EXE, os.path.isfile(EXE))
p = subprocess.Popen([EXE], cwd=APP)
print("启动 pid:", p.pid)

win = []
for i in range(20):
    time.sleep(1.5)
    win = windows_of({p.pid})
    if win:
        break

if win:
    print("✓ GUI 窗口已出现：")
    for t, pid, hwnd in win:
        print(f"   '{t}'  pid={pid}  hwnd={hwnd}")
else:
    print("✗ 未枚举到窗口，进程状态:", "alive" if p.poll() is None else f"exited {p.returncode}")

# 记录内存/线程
try:
    q = subprocess.run(["tasklist", "/FI", f"PID eq {p.pid}", "/FO", "LIST"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    for line in (q.stdout or "").splitlines():
        if any(k in line for k in ("内存", "Mem", "线程", "Thread")):
            print("  ", line.strip())
except Exception:
    pass

try:
    p.kill()
    print("已关闭测试进程")
except Exception:
    pass
