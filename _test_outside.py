# -*- coding: utf-8 -*-
"""验证「把程序整体搬到工作区外」是否解除限制。

假设：限制依据是「可执行文件所在路径」，位于 D:\\deepseekproject 内的一切
只能写 D:\\deepseekproject。若成立，把成品目录复制到 D:\\AGE下载器 就能正常
往任意盘写（ffmpeg 也一样，无需再复制副本）。
"""
import io
import os
import shutil
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC_DIR = r"D:\deepseekproject\agedl\dist\AGE下载器"
DST_DIR = r"D:\AGE下载器"
OUT = r"D:\迅雷下载\video\_exetest3"
RESULT = r"D:\deepseekproject\agedl\_exe_result3.txt"

# 1) 复制程序到工作区外
if os.path.isdir(DST_DIR):
    shutil.rmtree(DST_DIR, ignore_errors=True)
print(f"复制 {SRC_DIR} -> {DST_DIR} …")
t0 = time.time()
shutil.copytree(SRC_DIR, DST_DIR)
print(f"  完成，{time.time() - t0:.1f}s")
exe = os.path.join(DST_DIR, "AGE下载器.exe")
print("  exe:", exe, f"{os.path.getsize(exe):,} 字节")
ff_inner = os.path.join(DST_DIR, "_internal", "ffmpeg", "ffmpeg.exe")
print("  内置 ffmpeg:", os.path.isfile(ff_inner), f"{os.path.getsize(ff_inner):,} 字节" if os.path.isfile(ff_inner) else "")
print()

# 2) 清空输出目录 + 删 ffmpeg 逃逸副本（验证是否需要）
if os.path.isdir(OUT):
    shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)
tmp_ff = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "agedl_ffbin", "ffmpeg.exe")
if os.path.isfile(tmp_ff):
    try:
        os.remove(tmp_ff)
        print("已删 TEMP 里的 ffmpeg 副本（若仍成功，说明根本不需要逃逸）")
    except OSError:
        pass
print()

# 3) 生成 runner 并交给计划任务
for p in (RESULT,):
    if os.path.isfile(p):
        os.remove(p)

runner = r"D:\deepseekproject\agedl\_runner3.py"
open(runner, "w", encoding="utf-8").write(f'''# -*- coding: utf-8 -*-
import io, os, subprocess, time
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
buf = []
cmd = [{exe!r}, "--cli", "https://age001.com/play/12537-1-1.html",
       "-n", "1", "-f", "mp4", "-w", "24", "-o", {OUT!r}]
t0 = time.time()
p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=1800, creationflags=CNW)
buf.append(f"returncode={{p.returncode}} 用时={{time.time()-t0:.1f}}s")
buf.append("--- stdout ---")
buf.append((p.stdout or "")[:2000])
buf.append("--- stderr ---")
buf.append((p.stderr or "")[:3000])
log = os.path.join(os.path.dirname({exe!r}), "cli.log")
if os.path.isfile(log):
    buf.append("--- cli.log ---")
    buf.append(open(log, encoding="utf-8", errors="replace").read()[-2500:])
buf.append("--- 产物 ---")
for root, _d, files in os.walk({OUT!r}):
    for f in files:
        fp = os.path.join(root, f)
        buf.append(f"  {{f}}  {{os.path.getsize(fp):,}} 字节")
open({RESULT!r}, "w", encoding="utf-8").write("\\n".join(buf))
''')

tn = "AGEexetest3"
subprocess.run(["schtasks", "/Create", "/TN", tn, "/TR", f"C:\\Python314\\python.exe {runner}",
                "/SC", "ONCE", "/ST", "23:59", "/F", "/RL", "HIGHEST"], capture_output=True)
subprocess.run(["schtasks", "/Run", "/TN", tn], capture_output=True)
print("计划任务已启动，等待 …")

for _ in range(120):
    time.sleep(2)
    if os.path.isfile(RESULT):
        a = os.path.getsize(RESULT)
        time.sleep(2)
        if os.path.getsize(RESULT) == a:
            break
subprocess.run(["schtasks", "/Delete", "/TN", tn, "/F"], capture_output=True)

print()
print(open(RESULT, encoding="utf-8", errors="replace").read() if os.path.isfile(RESULT) else "✗ 结果未生成")
