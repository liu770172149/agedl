# -*- coding: utf-8 -*-
"""验证打包后的 exe：从 dist 目录运行，输出到「工作区外」的用户目录。

复现用户场景：exe 内置的 ffmpeg 位于 D:\\deepseekproject 内 → 被写权限限制 →
验证 escaped_ffmpeg 自动救场。
"""
import io
import os
import shutil
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

EXE = r"D:\deepseekproject\agedl\dist\AGE下载器\AGE下载器.exe"
OUT = r"D:\迅雷下载\video\_exetest"
TOOLS = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin"
FFPROBE = os.path.join(TOOLS, "ffprobe.exe")
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

assert os.path.isfile(EXE), EXE

# 清干净
if os.path.isdir(OUT):
    shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)

# 清理可能残留的 ffmpeg 副本，强制走一次复制流程
tmp_ff = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "agedl_ffbin", "ffmpeg.exe")
if os.path.isfile(tmp_ff):
    try:
        os.remove(tmp_ff)
        print("已删除旧 ffmpeg 副本，强制重走逃逸流程")
    except OSError as e:
        print("删副本失败:", e)
print()

print("exe  :", EXE)
print("输出 :", OUT)
print("输出目录在 workspace 外:", not OUT.lower().startswith(r"d:\deepseekproject"))
print("-" * 76)

cmd = [EXE, "--cli", "https://age001.com/play/12537-1-1.html",
       "-n", "1", "-f", "mp4", "-w", "24", "-o", OUT]
t0 = time.time()
p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=1800, creationflags=CNW)
dt = time.time() - t0
print(f"returncode = {p.returncode}   用时 {dt:.1f}s")
if (p.stdout or "").strip():
    print("--- stdout ---")
    print(p.stdout.strip()[:3000])
if (p.stderr or "").strip():
    print("--- stderr ---")
    print(p.stderr.strip()[:2000])

log = os.path.join(os.path.dirname(EXE), "cli.log")
if os.path.isfile(log):
    print("--- cli.log ---")
    print(open(log, encoding="utf-8", errors="replace").read()[-3000:])

print("-" * 76)
print("产物:")
found = []
for root, _dirs, files in os.walk(OUT):
    for f in files:
        fp = os.path.join(root, f)
        sz = os.path.getsize(fp)
        print(f"  {f}  {sz:,} 字节")
        if f.lower().endswith(".mp4"):
            found.append(fp)

if not found:
    print("✗ 没有 mp4 产物")
    sys.exit(1)

for fp in found:
    q = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                        "format=duration,format_name,size",
                        "-show_entries", "stream=codec_name,width,height",
                        "-of", "default=nw=1", fp],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300, creationflags=CNW)
    print("  ffprobe:", (q.stdout or "").replace("\n", " ").strip())
    d = subprocess.run([os.path.join(TOOLS, "ffmpeg.exe"), "-v", "error",
                        "-i", fp, "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800, creationflags=CNW)
    errs = [l for l in (d.stderr or "").strip().splitlines() if l.strip()]
    print(f"  全片解码: rc={d.returncode} 错误行={len(errs)}  {'✓ 通过' if d.returncode == 0 and not errs else '✗ 有问题'}")
    for e in errs[:3]:
        print("     ", e[:150])
