# -*- coding: utf-8 -*-
"""在 D:\\迅雷下载\\video 里复现：exe 封装失败 vs 源码成功。"""
import os
import shutil
import subprocess
import sys

TARGET = r"D:\迅雷下载\video"
RAW = os.path.join(TARGET, "命运奇异赝品 第01集.raw")
EXE_DIR = r"D:\deepseekproject\agedl\dist\AGE下载器"
EXE = os.path.join(EXE_DIR, "AGE下载器.exe")
FFMPEG_EXE = os.path.join(EXE_DIR, "_internal", "ffmpeg", "ffmpeg.exe")
FFMPEG_DEV = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"

print("目录:", TARGET, "exists:", os.path.isdir(TARGET))
print("raw:", os.path.getsize(RAW) if os.path.isfile(RAW) else "missing")

# 目录里现在有什么
files = os.listdir(TARGET)
print("目录文件数:", len(files))
print("  .raw 数:", sum(1 for f in files if f.endswith(".raw")))
print("  .mp4 数:", sum(1 for f in files if f.endswith(".mp4")))
print("  其他:", [f for f in files if not f.endswith((".raw", ".mp4"))][:10])

print()
print("=" * 60)
print("[测试1] 用 tools 的 ffmpeg（和之前成功的一致）写进迅雷目录")
dst = os.path.join(TARGET, "_probe_tools.mp4")
if os.path.exists(dst):
    os.remove(dst)
p = subprocess.run([FFMPEG_DEV, "-y", "-v", "error", "-i", RAW, "-c", "copy",
                    "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", dst],
                   capture_output=True, text=True, timeout=900)
print("  rc:", p.returncode, "stderr:", repr((p.stderr or "")[:300]))
print("  dst:", os.path.getsize(dst) if os.path.isfile(dst) else "MISSING")

print()
print("=" * 60)
print("[测试2] 用打包内置的 ffmpeg 写进迅雷目录")
dst2 = os.path.join(TARGET, "_probe_builtin.mp4")
if os.path.exists(dst2):
    os.remove(dst2)
p = subprocess.run([FFMPEG_EXE, "-y", "-v", "error", "-i", RAW, "-c", "copy",
                    "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", dst2],
                   capture_output=True, text=True, timeout=900)
print("  rc:", p.returncode, "stderr:", repr((p.stderr or "")[:300]))
print("  dst:", os.path.getsize(dst2) if os.path.isfile(dst2) else "MISSING")

print()
print("=" * 60)
print("[测试3] ffmpeg 版本对比")
for name, exe in (("tools", FFMPEG_DEV), ("builtin", FFMPEG_EXE)):
    r = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True,
                       text=True, timeout=30)
    print(f"  {name}: {(r.stdout or '').splitlines()[0] if r.stdout else '?'}")
