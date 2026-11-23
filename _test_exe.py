# -*- coding: utf-8 -*-
"""用打包好的 exe 跑一次真实下载，并验证产物。"""
import os
import shutil
import subprocess
import sys

EXE_DIR = r"D:\deepseekproject\agedl\dist\AGE下载器"
EXE = os.path.join(EXE_DIR, "AGE下载器.exe")
OUT = r"D:\deepseekproject\agedl_exe1"
FFPROBE = os.path.join(EXE_DIR, "_internal", "ffmpeg", "ffprobe.exe")

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)

print("exe:", EXE, "exists:", os.path.exists(EXE))
r = subprocess.run(
    [EXE, "--cli", "https://age001.com/play/12537-1-1.html",
     "-n", "1", "-f", "mp4", "-w", "24", "-o", OUT],
    cwd=EXE_DIR, capture_output=True, text=False, timeout=1800)
print("returncode:", r.returncode)
print("--- stdout ---")
print((r.stdout or b"").decode("utf-8", "replace")[-2000:])
print("--- stderr ---")
print((r.stderr or b"").decode("utf-8", "replace")[-2000:])

log = os.path.join(EXE_DIR, "cli.log")
if os.path.exists(log):
    print("--- cli.log ---")
    print(open(log, encoding="utf-8", errors="replace").read()[-2500:])

print("--- output files ---")
for f in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, f)
    print(f"  {f}  {os.path.getsize(p):,}")
    if f.lower().endswith(".mp4") and os.path.exists(FFPROBE):
        # 注意：ffprobe 是非白名单进程，读 .mp4 没问题（只有 .ts 被加密层接管）
        pr = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries",
             "format=duration,size,bit_rate", "-of", "default=nw=1", p],
            capture_output=True, text=False)
        print("    ffprobe:", (pr.stdout or pr.stderr).decode("utf-8", "replace").strip())
