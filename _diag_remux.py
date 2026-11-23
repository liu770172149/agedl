# -*- coding: utf-8 -*-
"""直接调用 core.remux_container 复现封装失败，拿到真实 returncode/stderr。"""
import os
import subprocess
import sys

sys.path.insert(0, r"D:\deepseekproject\agedl")
import core  # noqa: E402

RAW = r"D:\迅雷下载\video\命运奇异赝品 第01集.raw"
DST = r"D:\deepseekproject\_diag_test.mp4"

print("raw exists:", os.path.isfile(RAW), "size:", os.path.getsize(RAW))
print("ffmpeg:", core.find_ffmpeg())
print()

# 手动复现 remux_container 内部完全相同的调用
ff = core.find_ffmpeg()
tmp = DST + ".part" + ".mp4"
base = ["-i", RAW, "-c", "copy", "-movflags", "+faststart", tmp]
args = base[:2] + ["-bsf:a", "aac_adtstoasc"] + base[2:]

print("cmd:", [ff] + args[:4], "...", args[-1:])
for attempt, a in enumerate([args, base], 1):
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f"--- attempt {attempt} ---")
    p = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error"] + a,
                       capture_output=True, text=True, timeout=600,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print("  returncode:", p.returncode)
    print("  stderr:", repr((p.stderr or "")[:600]))
    print("  tmp exists:", os.path.isfile(tmp),
          "size:", os.path.getsize(tmp) if os.path.isfile(tmp) else 0)

print()
print("=== 现在用 core.remux_container 本体 ===")
logs = []
ok = core.remux_container(ff, RAW, DST, on_log=lambda m: logs.append(m))
print("  result:", ok)
for m in logs:
    print("  log:", m)
print("  dst exists:", os.path.isfile(DST),
      "size:", os.path.getsize(DST) if os.path.isfile(DST) else 0)
