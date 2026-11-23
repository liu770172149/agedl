# -*- coding: utf-8 -*-
"""找出 ffmpeg 可写范围的规律。"""
import os
import subprocess

FFMPEG = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
SRC = r"D:\迅雷下载\video\命运奇异赝品 第01集.raw"

cases = [
    r"D:\deepseekproject\agedl_probe",
    r"D:\deepseekproject",
    "D:\\",
    r"D:\_perm_probe",
    r"D:\迅雷下载\video",
    r"D:\迅雷下载",
    r"C:\Users\Admin\Downloads",
    r"C:\Users\Admin\_perm_probe",
    r"C:\Windows\Temp\_perm_probe",
    os.environ.get("TEMP", r"C:\Users\Admin\AppData\Local\Temp") + r"\_perm_probe",
]
if os.path.isdir("E:\\"):
    cases.append(r"E:\_perm_probe")

print(f"{'目录':<46} {'ffmpeg':<10} {'python':<10}")
print("-" * 70)
for d in cases:
    try:
        os.makedirs(d, exist_ok=True)
    except OSError as e:
        print(f"{d:<46} 建目录失败 {e}")
        continue
    # Python 写
    py_ok = False
    try:
        pp = os.path.join(d, "_py.mp4")
        with open(pp, "wb") as f:
            f.write(b"\x00" * 4096)
        py_ok = True
        os.remove(pp)
    except Exception:
        pass
    # ffmpeg 写
    dst = os.path.join(d, "_ff.mp4")
    try:
        if os.path.exists(dst):
            os.remove(dst)
    except OSError:
        pass
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-t", "3", "-i", SRC,
                        "-c", "copy", dst], capture_output=True, text=True, timeout=180)
    ff_ok = os.path.isfile(dst) and os.path.getsize(dst) > 0
    if ff_ok:
        try:
            os.remove(dst)
        except OSError:
            pass
    print(f"{d:<46} {'OK' if ff_ok else 'DENIED':<10} {'OK' if py_ok else 'FAIL':<10}")
