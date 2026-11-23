# -*- coding: utf-8 -*-
"""用打过补丁的 core.remux_container 直接处理用户目录里的真实 .raw 文件。"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, r"D:\deepseekproject\agedl")
import core  # noqa: E402

SRC = r"D:\迅雷下载\video\命运奇异赝品 第01集.raw"
DST = r"D:\迅雷下载\video\命运奇异赝品 第01集.mp4"

print("源:", SRC, f"{os.path.getsize(SRC):,} 字节")
print("目标:", DST)
print()

logs = []
ff = core.find_ffmpeg()
print("find_ffmpeg() ->", ff)
print("版本:", core.ffmpeg_version(ff))
print()

ok = core.remux_container(ff, SRC, DST, on_log=lambda m: (logs.append(m), print(m)))
print()
print("返回值:", ok)
if os.path.isfile(DST):
    print(f"产物: {os.path.getsize(DST):,} 字节")
    import subprocess
    p = subprocess.run([ff.replace("ffmpeg.exe", "ffprobe.exe"), "-v", "error",
                        "-show_entries", "format=duration,format_name,size,bit_rate",
                        "-of", "default=nw=1", DST],
                       capture_output=True, text=True, timeout=120)
    print("ffprobe:", (p.stdout or "").replace("\n", " ").strip())
