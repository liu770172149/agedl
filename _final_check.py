# -*- coding: utf-8 -*-
"""最终验收：exe 启动 GUI + 端到端下载（mkv 与 mp4 各一次）。"""
import os
import shutil
import subprocess
import time

EXE_DIR = r"D:\deepseekproject\agedl\dist\AGE下载器"
EXE = os.path.join(EXE_DIR, "AGE下载器.exe")
FFPROBE = os.path.join(EXE_DIR, "_internal", "ffmpeg", "ffprobe.exe")

print("=" * 60)
print("[1] GUI 启动检查")
p = subprocess.Popen([EXE], cwd=EXE_DIR)
time.sleep(6)


def window_titles(pid):
    """枚举某进程的所有顶层窗口标题（含子进程）。"""
    code = r'''
import ctypes, ctypes.wintypes as w, sys
pid = int(sys.argv[1])
u = ctypes.windll.user32
res = []
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
def cb(h, l):
    p = w.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(p))
    if p.value == pid:
        n = u.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            res.append((h, bool(u.IsWindowVisible(h)), b.value))
    return True
u.EnumWindows(CB(cb), 0)
print(res)
'''
    r = subprocess.run(["C:/Python314/python.exe", "-c", code, str(pid)],
                       capture_output=True, text=False)
    return (r.stdout or r.stderr).decode("utf-8", "replace").strip()


# onefile 会是双进程；onedir 单进程为主，但主进程会派生
kids = []
try:
    out = subprocess.run(
        ["C:/Windows/System32/wbem/WMIC.exe", "process", "where",
         "name='AGE下载器.exe'", "get", "ProcessId,ParentProcessId", "/format:csv"],
        capture_output=True, text=False, timeout=20).stdout.decode("utf-8", "replace")
    print("  running procs:", " | ".join(l.strip() for l in out.splitlines() if l.strip()))
except Exception as e:
    print("  wmic failed:", e)

print("  windows(pid=%d):" % p.pid, window_titles(p.pid))
p.terminate()
try:
    p.wait(timeout=10)
except subprocess.TimeoutExpired:
    p.kill()

print()
print("=" * 60)
print("[2] 端到端下载 MKV")
OUT2 = r"D:\deepseekproject\agedl_final_mkv"
shutil.rmtree(OUT2, ignore_errors=True)
r = subprocess.run([EXE, "--cli", "https://age001.com/play/12537-1-1.html",
                    "-n", "1", "-f", "mkv", "-w", "24", "-o", OUT2],
                   cwd=EXE_DIR, capture_output=True, text=False, timeout=1800)
print("  returncode:", r.returncode)
for f in sorted(os.listdir(OUT2)) if os.path.isdir(OUT2) else []:
    fp = os.path.join(OUT2, f)
    if os.path.isfile(fp):
        print(f"  {f}  {os.path.getsize(fp):,}")
        pr = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                             "format=duration,format_name", "-of", "default=nw=1", fp],
                            capture_output=True, text=False)
        print("    ->", (pr.stdout or pr.stderr).decode("utf-8", "replace").strip().replace("\n", " "))
