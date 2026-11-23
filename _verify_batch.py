# -*- coding: utf-8 -*-
"""校验转换后的 mp4：ffprobe 元信息 + 全片解码零错误。"""
import glob
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TOOLS = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin"
FFMPEG = os.path.join(TOOLS, "ffmpeg.exe")
FFPROBE = os.path.join(TOOLS, "ffprobe.exe")
assert os.path.isfile(FFMPEG), FFMPEG
assert os.path.isfile(FFPROBE), FFPROBE

DIR = r"D:\迅雷下载\video"
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

files = sorted(glob.glob(os.path.join(DIR, "*.mp4")))
print(f"共 {len(files)} 个 mp4\n")
print(f"{'文件':38s} {'大小MB':>9} {'时长':>10} {'分辨率':>11} {'视频码率':>10} {'解码':>6}")
print("-" * 92)

bad = []
total = 0
for f in files:
    sz = os.path.getsize(f)
    total += sz
    p = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,width,height,bit_rate",
                        "-of", "default=nw=1", f],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120, creationflags=CNW)
    dur = "?"
    res = "?"
    vbr = "?"
    for line in (p.stdout or "").splitlines():
        if line.startswith("duration="):
            try:
                dur = f"{float(line.split('=')[1]):.0f}s"
            except ValueError:
                pass
        if line.startswith("width="):
            w = line.split("=")[1]
            res = w + "x"
        if line.startswith("height=") and res.endswith("x"):
            res += line.split("=")[1]
        if line.startswith("bit_rate=") and vbr == "?":
            try:
                vbr = f"{int(line.split('=')[1]) // 1000}k"
            except ValueError:
                pass
    # 全片解码
    d = subprocess.run([FFMPEG, "-v", "error", "-i", f, "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800, creationflags=CNW)
    errs = [l for l in (d.stderr or "").strip().splitlines() if l.strip()]
    status = "OK" if d.returncode == 0 and not errs else f"ERR{len(errs)}"
    if status != "OK":
        bad.append((os.path.basename(f), errs[:2]))
    print(f"{os.path.basename(f):38s} {sz / 1048576:9.1f} {dur:>10} {res:>11} {vbr:>10} {status:>6}")

print("-" * 92)
print(f"合计 {total / 1073741824:.2f} GB")
print(f"解码异常 {len(bad)} 个")
for n, e in bad:
    print("  ", n)
    for x in e:
        print("     ", x[:150])
