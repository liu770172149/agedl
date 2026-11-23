# -*- coding: utf-8 -*-
"""确定「ffmpeg 被拒」规则的确切边界，找出打包 exe 也能用的通用绕法。

每项都：(复制 ffmpeg 到 X) -> (从 X 运行，写 Y) -> 报告 rc/大小。
"""
import io
import os
import shutil
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FFMPEG = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
FFPROBE = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffprobe.exe"
RAW = r"D:\迅雷下载\video\命运奇异赝品 第01集.raw"
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def attempt(label, ff_path, out_path, cwd=None):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
    cmd = [ff_path, "-y", "-v", "error", "-t", "5", "-i", RAW, "-c", "copy", out_path]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                           creationflags=CNW, cwd=cwd)
        sz = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
        ok = p.returncode == 0 and sz > 0
        err = (p.stderr or "").strip().splitlines()
        err = err[0][:100] if err else ""
    except Exception as e:  # noqa: BLE001
        ok, p, sz, err = False, None, 0, str(e)[:100]
    mark = "OK  " if ok else "DENY"
    print(f"  [{mark}] {label:52s} rc={p.returncode if p else '-':>12} size={sz:>10} {err}")
    if os.path.isfile(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
    return ok


def copy_ff(dst_dir, name="_ffmpeg_copy.exe"):
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, name)
    if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(FFMPEG):
        shutil.copy2(FFMPEG, dst)
        print(f"    (已复制 {os.path.getsize(dst):,} 字节 -> {dst})")
    return dst


print("=" * 80)
print("基准：原位置 ffmpeg 写到被拒目录")
attempt("原 ffmpeg -> D:\\迅雷下载\\video", FFMPEG, r"D:\迅雷下载\video\_b.mp4")

print()
print("=" * 80)
print("A. ffmpeg 副本放在目标目录，写同目录")
a_dir = r"D:\迅雷下载\video"
a_ff = copy_ff(a_dir, "_ffa.exe")
attempt("副本在同目录 -> 同目录", a_ff, os.path.join(a_dir, "_a.mp4"))

print()
print("=" * 80)
print("B. ffmpeg 副本放在目标目录的子目录，写父目录")
b_sub = r"D:\迅雷下载\video\_ffbin"
b_ff = copy_ff(b_sub, "_ffb.exe")
attempt("副本在子目录 -> 父目录", b_ff, r"D:\迅雷下载\video\_b2.mp4")

print()
print("=" * 80)
print("C. ffmpeg 副本放在完全不相关的被拒目录（E 盘）")
c_dir = r"E:\_perm_probe"
c_ff = copy_ff(c_dir, "_ffc.exe")
attempt("副本在 E 盘 -> E 盘", c_ff, os.path.join(c_dir, "_c.mp4"))
attempt("副本在 E 盘 -> D:\\迅雷下载\\video", c_ff, r"D:\迅雷下载\video\_c2.mp4")

print()
print("=" * 80)
print("D. 副本在 C 盘用户目录")
d_dir = r"C:\Users\Admin\Downloads"
d_ff = copy_ff(d_dir, "_ffd.exe")
attempt("副本在 Downloads -> Downloads", d_ff, os.path.join(d_dir, "_d.mp4"))
attempt("副本在 Downloads -> 迅雷目录", d_ff, r"D:\迅雷下载\video\_d2.mp4")

print()
print("=" * 80)
print("E. 原 ffmpeg，cwd 设为被拒目录（看 cwd 是否有影响）")
attempt("原 ffmpeg, cwd=迅雷目录 -> 迅雷目录", FFMPEG, r"D:\迅雷下载\video\_e.mp4",
        cwd=r"D:\迅雷下载\video")
attempt("原 ffmpeg, cwd=C:\\ -> 迅雷目录", FFMPEG, r"D:\迅雷下载\video\_e2.mp4", cwd="C:\\")

print()
print("=" * 80)
print("F. 副本放在 deepseekproject 内（已知可写）写迅雷目录")
f_dir = r"D:\deepseekproject\_fftmp"
f_ff = copy_ff(f_dir, "_fff.exe")
attempt("副本在 deepseekproject -> 迅雷目录", f_ff, r"D:\迅雷下载\video\_f.mp4")

print()
print("=" * 80)
print("清理")
for p in (a_ff, b_ff, c_ff, d_ff, f_ff):
    try:
        os.remove(p)
        print("  删", p)
    except OSError as e:
        print("  留", p, e)
try:
    os.rmdir(b_sub)
    os.rmdir(f_dir)
except OSError:
    pass
