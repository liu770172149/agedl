# -*- coding: utf-8 -*-
"""验证「ffmpeg 副本放在非 deepseekproject 目录即可全盘写」这一规律，
并确认最稳的落点（用户 TEMP / LOCALAPPDATA / 目标目录旁）。

同时测试：从这些位置起的副本能否写 D:\\迅雷下载\\video。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FFMPEG = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
RAW = r"D:\迅雷下载\video\命运奇异赝品 第01集.raw"
TARGET = r"D:\迅雷下载\video"
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_from(ff_path, out_path):
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
    cmd = [ff_path, "-y", "-v", "error", "-t", "5", "-i", RAW, "-c", "copy", out_path]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=CNW)
        sz = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
        ok = p.returncode == 0 and sz > 0
        err = (p.stderr or "").strip().splitlines()
        err = err[0][:90] if err else ""
    except Exception as e:  # noqa: BLE001
        ok, p, sz, err = False, None, 0, str(e)[:90]
    return ok, sz, err


def trial(label, host_dir):
    host_dir = os.path.expandvars(host_dir)
    os.makedirs(host_dir, exist_ok=True)
    ff = os.path.join(host_dir, "_fftest.exe")
    try:
        if not os.path.isfile(ff):
            shutil.copy2(FFMPEG, ff)
    except OSError as e:
        print(f"  [复制失败] {label:44s} {e}")
        return
    out = os.path.join(TARGET, "_x.mp4")
    ok, sz, err = run_from(ff, out)
    print(f"  [{'OK  ' if ok else 'DENY'}] {label:44s} ff={host_dir:46s} size={sz:>9} {err}")
    if os.path.isfile(out):
        try:
            os.remove(out)
        except OSError:
            pass
    for _ in range(3):
        try:
            os.remove(ff)
            break
        except OSError:
            import time
            time.sleep(0.5)


print("=" * 96)
print("目标输出目录:", TARGET, "(已知被「受控 ffmpeg」拒绝)")
print("=" * 96)

trial("A 用户 TEMP", r"%LOCALAPPDATA%\Temp\AGEDL_test")
trial("B LOCALAPPDATA", r"%LOCALAPPDATA%\AGEDL_test")
trial("C 目标目录自身", TARGET)
trial("D 目标目录子目录", os.path.join(TARGET, "_bin"))
trial("E 程序数据目录", r"%APPDATA%\AGEDL_test")
trial("F C 盘根", r"C:\AGEDL_test")
trial("G D 盘根", r"D:\AGEDL_test")
trial("H deepseekproject（对照，预期 DENY）", r"D:\deepseekproject\_ffctl")

print()
print("清理临时目录")
for d in (r"%LOCALAPPDATA%\Temp\AGEDL_test", r"%LOCALAPPDATA%\AGEDL_test",
          r"%APPDATA%\AGEDL_test", r"C:\AGEDL_test", r"D:\AGEDL_test",
          r"D:\deepseekproject\_ffctl", os.path.join(TARGET, "_bin")):
    d = os.path.expandvars(d)
    try:
        os.rmdir(d)
        print("  删", d)
    except OSError:
        pass
