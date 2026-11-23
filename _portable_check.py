# -*- coding: utf-8 -*-
"""便携包最终验收：从全新解压目录启动 GUI + 跑一次真实下载。"""
import os
import subprocess
import sys
import time

BASE = r"D:\deepseekproject\_portable_test"
EXE = os.path.join(BASE, "AGE下载器.exe")
FFPROBE = os.path.join(BASE, "_internal", "ffmpeg", "ffprobe.exe")
OUT = r"D:\deepseekproject\_portable_out"

print("=" * 64)
print("[A] 从解压目录启动 GUI")
p = subprocess.Popen([EXE], cwd=BASE)
time.sleep(7)

code = r'''
import ctypes, ctypes.wintypes as w, sys
pid = int(sys.argv[1]); u = ctypes.windll.user32; res=[]
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
def cb(h,l):
    q = w.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(q))
    if q.value == pid:
        n = u.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n+1); u.GetWindowTextW(h,b,n+1)
            if u.IsWindowVisible(h): res.append(b.value)
    return True
u.EnumWindows(CB(cb), 0); print("|".join(res))
'''
r = subprocess.run([sys.executable, "-c", code, str(p.pid)],
                   capture_output=True, text=False)
vis = (r.stdout or b"").decode("utf-8", "replace").strip()
print("  visible windows:", vis or "(none)")
print("  => GUI OK" if "AGE动漫" in vis else "  => GUI FAIL")
p.terminate()
try:
    p.wait(timeout=8)
except subprocess.TimeoutExpired:
    p.kill()

print()
print("=" * 64)
print("[B] 真实下载（第2集，验证换集也能工作）")
import shutil
shutil.rmtree(OUT, ignore_errors=True)
t0 = time.time()
r = subprocess.run([EXE, "--cli", "https://age001.com/play/12537-1-1.html",
                    "-n", "2", "-f", "mp4", "-w", "20", "-o", OUT],
                   cwd=BASE, capture_output=True, text=False, timeout=1800)
print("  returncode:", r.returncode, " elapsed: %.1fs" % (time.time() - t0))
if os.path.isdir(OUT):
    for f in sorted(os.listdir(OUT)):
        fp = os.path.join(OUT, f)
        if not os.path.isfile(fp):
            continue
        print(f"  {f}  {os.path.getsize(fp):,} bytes")
        pr = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                             "format=duration,format_name:stream=codec_name,width,height",
                             "-of", "default=nw=1", fp],
                            capture_output=True, text=False)
        print("   ", (pr.stdout or pr.stderr).decode("utf-8", "replace").strip().replace("\n", " | "))
else:
    print("  !! 输出目录不存在")
