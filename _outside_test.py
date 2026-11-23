# -*- coding: utf-8 -*-
"""脱离当前进程树测试：写结果到文件，供事后读取。"""
import os
import subprocess
import sys

FFMPEG = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
SRC = r"D:\迅雷下载\video\命运奇异赝品 第01集.raw"
LOG = r"D:\deepseekproject\_outside_test.txt"

lines = [f"python={sys.executable}", f"cwd={os.getcwd()}", f"ppid={os.getppid()}"]

for d in (r"D:\迅雷下载\video", r"D:\deepseekproject"):
    dst = os.path.join(d, "_outside_probe.mp4")
    try:
        if os.path.exists(dst):
            os.remove(dst)
    except OSError:
        pass
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-t", "3", "-i", SRC,
                        "-c", "copy", dst], capture_output=True, text=True, timeout=180)
    ok = os.path.isfile(dst) and os.path.getsize(dst) > 0
    lines.append(f"{d} -> rc={r.returncode} ok={ok} err={((r.stderr or '').strip().splitlines() or [''])[0][:120]}")
    if ok:
        try:
            os.remove(dst)
        except OSError:
            pass

with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
