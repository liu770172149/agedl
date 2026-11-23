# -*- coding: utf-8 -*-
"""对 exe 产出的 MP4 做全片解码校验 + 抽帧，证明内容完整。"""
import os
import subprocess

EXE_DIR = r"D:\deepseekproject\agedl\dist\AGE下载器"
FFMPEG = os.path.join(EXE_DIR, "_internal", "ffmpeg", "ffmpeg.exe")
FFPROBE = os.path.join(EXE_DIR, "_internal", "ffmpeg", "ffprobe.exe")
MP4 = r"D:\deepseekproject\agedl_exe1\命运奇异赝品 第01集.mp4"
FRAMES = r"D:\deepseekproject\frames_exe"

print("size:", f"{os.path.getsize(MP4):,}")

# 1) 流信息
r = subprocess.run([FFPROBE, "-v", "error", "-show_streams",
                    "-show_format", "-of", "default=nw=1", MP4],
                   capture_output=True, text=False)
for line in (r.stdout or b"").decode("utf-8", "replace").splitlines():
    if line.split("=")[0] in ("codec_name", "codec_type", "width", "height",
                              "duration", "bit_rate", "avg_frame_rate",
                              "sample_rate", "channels", "format_name"):
        print("  ", line)

# 2) 全片解码校验
print("--- full decode check ---")
r = subprocess.run([FFMPEG, "-v", "error", "-i", MP4, "-f", "null", "-"],
                   capture_output=True, text=False, timeout=1800)
err = (r.stderr or b"").decode("utf-8", "replace").strip()
print("returncode:", r.returncode)
print("errors:", repr(err[:500]) if err else "NONE  (零错误)")

# 3) 抽帧
os.makedirs(FRAMES, exist_ok=True)
for t in (30, 500, 900, 1400):
    dst = os.path.join(FRAMES, f"exe_{t:05d}.jpg")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(t), "-i", MP4,
                    "-frames:v", "1", "-q:v", "3", dst],
                   capture_output=True, timeout=180)
    print(f"  frame @{t}s ->", os.path.exists(dst) and f"{os.path.getsize(dst):,} bytes")
