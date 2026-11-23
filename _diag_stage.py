# -*- coding: utf-8 -*-
"""找出在 DLP 拒绝目录里让 ffmpeg 产出文件的可行路径。

测试项：
1) 不同扩展名
2) Python 先创建空文件，ffmpeg 覆盖写
3) 把 ffmpeg.exe 复制到被拒目录后，用它写同目录
4) ffmpeg 输出到 stdout 管道，Python 写盘
"""
import io
import os
import shutil
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FFMPEG = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
RAW = r"D:\迅雷下载\video\命运奇异赝品 第01集.raw"
DENIED = r"D:\迅雷下载\video"
ALLOWED = r"D:\deepseekproject"

print("源:", RAW, os.path.getsize(RAW), "字节")
print()

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ff_write(target, ff=FFMPEG, extra=None):
    base = [ff, "-y", "-v", "error", "-t", "5", "-i", RAW, "-c", "copy"]
    if extra:
        base += extra
    p = subprocess.run(base + [target], capture_output=True, text=True, timeout=300,
                       creationflags=CREATE_NO_WINDOW)
    ok = os.path.isfile(target) and os.path.getsize(target) > 0
    size = os.path.getsize(target) if os.path.isfile(target) else 0
    err = (p.stderr or "").strip().splitlines()
    return ok, p.returncode, size, (err[0][:110] if err else "")


print("=" * 78)
print("测试 1：被拒目录下不同扩展名")
for ext in (".mp4", ".mkv", ".dat", ".m4v"):
    t = os.path.join(DENIED, "_t_ext" + ext)
    if os.path.exists(t):
        os.remove(t)
    ok, rc, size, err = ff_write(t)
    print(f"  {ext:6s} ok={ok!s:5s} rc={rc} size={size} {err}")
    if os.path.exists(t):
        os.remove(t)

print()
print("=" * 78)
print("测试 2：Python 先建空文件，ffmpeg 覆盖写（-y）")
t = os.path.join(DENIED, "_t_pre.mp4")
with open(t, "wb") as f:
    f.write(b"\x00" * 16)
print(f"  预创建: {os.path.getsize(t)} 字节")
ok, rc, size, err = ff_write(t)
print(f"  结果  ok={ok!s:5s} rc={rc} size={size} {err}")
if os.path.exists(t):
    os.remove(t)

print()
print("=" * 78)
print("测试 3：把 ffmpeg.exe 复制到被拒目录，用它写同目录")
local_ff = os.path.join(DENIED, "_t_ffmpeg.exe")
try:
    shutil.copy2(FFMPEG, local_ff)
    print(f"  已复制: {os.path.getsize(local_ff)} 字节")
    t = os.path.join(DENIED, "_t_local.mp4")
    if os.path.exists(t):
        os.remove(t)
    ok, rc, size, err = ff_write(t, ff=local_ff)
    print(f"  结果  ok={ok!s:5s} rc={rc} size={size} {err}")
    if os.path.exists(t):
        os.remove(t)
except OSError as e:
    print("  复制失败:", e)
finally:
    try:
        os.remove(local_ff)
    except OSError:
        pass

print()
print("=" * 78)
print("测试 4：ffmpeg 输出到 stdout 管道，Python 写盘（fragmented mp4）")
t = os.path.join(DENIED, "_t_pipe.mp4")
if os.path.exists(t):
    os.remove(t)
cmd = [FFMPEG, "-y", "-v", "error", "-t", "20", "-i", RAW, "-c", "copy",
       "-movflags", "frag_keyframe+empty_moov+default_base_moof",
       "-f", "mp4", "pipe:1"]
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     creationflags=CREATE_NO_WINDOW)
n = 0
try:
    with open(t, "wb") as f:
        while True:
            chunk = p.stdout.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            n += len(chunk)
    p.wait(timeout=300)
    err = (p.stderr.read() or b"").decode("utf-8", "replace").strip()
    print(f"  收到 {n} 字节, rc={p.returncode}, 落盘={os.path.getsize(t) if os.path.exists(t) else 0}")
    if err:
        print("  stderr:", err.splitlines()[-1][:150])
except Exception as e:
    print("  异常:", e)
    p.kill()
if os.path.exists(t):
    print(f"  ✓ 管道方式成功，文件 {os.path.getsize(t)} 字节")
    probe = subprocess.run([FFMPEG.replace("ffmpeg.exe", "ffprobe.exe"), "-v", "error",
                            "-show_entries", "format=duration,format_name,size",
                            "-of", "default=nw=1", t],
                           capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    print("  ffprobe:", (probe.stdout or "").replace("\n", " ").strip())
    os.remove(t)

print()
print("=" * 78)
print("测试 5：stdout 管道 + mkv 封装（matroska 天然可流式）")
t = os.path.join(DENIED, "_t_pipe.mkv")
if os.path.exists(t):
    os.remove(t)
cmd = [FFMPEG, "-y", "-v", "error", "-t", "20", "-i", RAW, "-c", "copy",
       "-f", "matroska", "pipe:1"]
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     creationflags=CREATE_NO_WINDOW)
n = 0
try:
    with open(t, "wb") as f:
        while True:
            chunk = p.stdout.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            n += len(chunk)
    p.wait(timeout=300)
    err = (p.stderr.read() or b"").decode("utf-8", "replace").strip()
    print(f"  收到 {n} 字节, rc={p.returncode}, 落盘={os.path.getsize(t) if os.path.exists(t) else 0}")
    if err:
        print("  stderr:", err.splitlines()[-1][:150])
except Exception as e:
    print("  异常:", e)
    p.kill()
if os.path.exists(t):
    print(f"  ✓ 管道方式成功，文件 {os.path.getsize(t)} 字节")
    os.remove(t)

print()
print("=" * 78)
print("测试 6：可写目录（对照）确认 ffmpeg 直写仍正常")
t = os.path.join(ALLOWED, "_t_ctl.mp4")
ok, rc, size, err = ff_write(t)
print(f"  ok={ok!s:5s} rc={rc} size={size} {err}")
if os.path.exists(t):
    os.remove(t)
