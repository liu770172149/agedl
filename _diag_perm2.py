# -*- coding: utf-8 -*-
"""继续定位：ffmpeg 在迅雷目录写不进去，但 Python 能写。"""
import os
import subprocess

T = r"D:\迅雷下载\video"
FFMPEG = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"

print("=== 目录属性 ===")
st = os.stat(T)
print("  mode:", oct(st.st_mode), "attrs:", getattr(st, "st_file_attributes", "n/a"))

print()
print("=== ffmpeg 在 4 个目录写入测试 ===")
src = os.path.join(T, "命运奇异赝品 第01集.raw")
cases = [
    (T, "迅雷/video"),
    (r"D:\迅雷下载", "迅雷根"),
    (r"D:\deepseekproject", "项目目录"),
    (r"C:\Users\Admin\Downloads", "用户下载"),
    (r"D:\deepseekproject\agedl_exe1", "曾成功目录"),
]
for d, label in cases:
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, "_ff_probe.mp4")
    try:
        if os.path.exists(dst):
            os.remove(dst)
    except OSError as e:
        print(f"  {label:12s} 旧文件删不掉: {e}")
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-t", "5", "-i", src,
                        "-c", "copy", dst],
                       capture_output=True, text=True, timeout=300)
    ok = os.path.isfile(dst) and os.path.getsize(dst) > 0
    msg = ((r.stderr or "").strip().splitlines() or [""])[0][:100]
    print(f"  {label:12s} rc={r.returncode:<12} written={str(ok):5s} {msg}")
    if ok:
        try:
            os.remove(dst)
        except OSError:
            pass

print()
print("=== Python 在迅雷目录写 .mp4（对照）===")
p = os.path.join(T, "_py_probe.mp4")
try:
    with open(p, "wb") as f:
        f.write(b"\x00" * (4 * 1024 * 1024))
    print("  Python 写 .mp4 OK:", os.path.getsize(p))
    os.remove(p)
except Exception as e:
    print("  Python 写 .mp4 失败:", e)

print()
print("=== 直接读迅雷目录的 ACL ===")
r = subprocess.run(["cmd", "/c", "icacls", T], capture_output=True, text=False)
print((r.stdout or b"").decode("gbk", "replace")[:1500])
