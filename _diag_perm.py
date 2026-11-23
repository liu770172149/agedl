# -*- coding: utf-8 -*-
"""定位：为什么 ffmpeg 在 D:\\迅雷下载\\video 无写权限，而 Python 能写。"""
import os
import stat
import subprocess

T = r"D:\迅雷下载\video"
FFMPEG = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"

print("=== 1. 目录基本属性 ===")
st = os.stat(T)
print("  mode:", oct(st.st_mode), "readonly:", not (st.st_mode & stat.S_IWRITE))
print("  attrs via os.stat:", st.st_file_attributes if hasattr(st, "st_file_attributes") else "n/a")

print()
print("=== 2. Python 在同一目录写文件 ===")
probe = os.path.join(T, "_py_probe.txt")
try:
    with open(probe, "wb") as f:
        f.write(b"hello world " * 100)
    print("  Python 写 OK:", os.path.getsize(probe))
except Exception as e:
    print("  Python 写失败:", e)
try:
    os.remove(probe)
except OSError:
    pass

print()
print("=== 3. PowerShell 在同一目录写文件 ===")
ps = os.path.join(T, "_ps_probe.txt")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Content -LiteralPath '{ps}' -Value 'hello' -Encoding ASCII"],
                   capture_output=True, text=True)
print("  rc:", r.returncode, "err:", (r.stderr or "")[:200].strip())
print("  文件存在:", os.path.isfile(ps))
try:
    os.remove(ps)
except OSError:
    pass

print()
print("=== 4. 目录内文件的属主/属性（前3个）===")
r = subprocess.run(["cmd", "/c", "dir", "/a", T], capture_output=True, text=False)
print((r.stdout or b"").decode("gbk", "replace")[:1200])

print()
print("=== 5. 测试 ffmpeg 写入不同目录 ===")
cases = [
    (r"D:\迅雷下载\video", "迅雷目录"),
    (r"D:\迅雷下载", "迅雷根"),
    (r"D:\deepseekproject", "项目目录"),
    (r"C:\Users\Admin\Downloads", "用户下载"),
]
src = os.path.join(T, "命运奇异赝品 第01集.raw")
for d, label in cases:
    if not os.path.isdir(d):
        print(f"  {label}: 目录不存在"); continue
    dst = os.path.join(d, "_ff_probe.mp4")
    try:
        if os.path.exists(dst):
            os.remove(dst)
    except OSError as e:
        print(f"  {label}: 无法删除旧文件 {e}"); continue
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-t", "5", "-i", src,
                        "-c", "copy", dst],
                       capture_output=True, text=True, timeout=300)
    ok = os.path.isfile(dst) and os.path.getsize(dst) > 0
    print(f"  {label:10s} rc={r.returncode:>12} written={ok}  {((r.stderr or '').strip().splitlines() or [''])[0][:90]}")
    if ok:
        os.remove(dst)
