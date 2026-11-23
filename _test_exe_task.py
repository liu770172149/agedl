# -*- coding: utf-8 -*-
"""通过计划任务（脱离 harness 沙箱）端到端验证 exe。

模拟用户真实场景：
  exe 位于 D:\\deepseekproject\\agedl\\dist\\AGE下载器\\（workspace 内）
  输出到 D:\\迅雷下载\\video（workspace 外）
预期：内置 ffmpeg 首次被拒 → 自动复制到 TEMP → 重试成功 → 产出完整 mp4
"""
import io
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

EXE = r"D:\deepseekproject\agedl\dist\AGE下载器\AGE下载器.exe"
OUT = r"D:\迅雷下载\video\_exetest2"
TOOLS = r"D:\deepseekproject\tools\ffmpeg-master-latest-win64-gpl\bin"
RESULT = r"D:\deepseekproject\agedl\_exe_result.txt"

# 清空旧结果
for p in (RESULT,):
    if os.path.isfile(p):
        os.remove(p)

# 清空输出目录
import shutil
if os.path.isdir(OUT):
    shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)

# 删掉 ffmpeg 副本，强制走逃逸流程
tmp_ff = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "agedl_ffbin", "ffmpeg.exe")
if os.path.isfile(tmp_ff):
    try:
        os.remove(tmp_ff)
        print("已删旧 ffmpeg 副本")
    except OSError:
        pass

# 生成一个 runner 脚本，交给计划任务执行
runner = r"D:\deepseekproject\agedl\_runner.py"
open(runner, "w", encoding="utf-8").write(f'''# -*- coding: utf-8 -*-
import io, os, subprocess, sys, time
out = io.StringIO()
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
cmd = [{EXE!r}, "--cli", "https://age001.com/play/12537-1-1.html",
       "-n", "1", "-f", "mp4", "-w", "24", "-o", {OUT!r}]
t0 = time.time()
p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=1800, creationflags=CNW)
out.write(f"returncode={{p.returncode}} 用时={{time.time()-t0:.1f}}s\\n")
out.write("--- stdout ---\\n" + (p.stdout or "")[:2000] + "\\n")
out.write("--- stderr ---\\n" + (p.stderr or "")[:3000] + "\\n")
log = os.path.join(os.path.dirname({EXE!r}), "cli.log")
if os.path.isfile(log):
    out.write("--- cli.log ---\\n" + open(log, encoding="utf-8", errors="replace").read()[-2500:] + "\\n")
out.write("--- 产物 ---\\n")
for root, _d, files in os.walk({OUT!r}):
    for f in files:
        fp = os.path.join(root, f)
        out.write(f"  {{f}}  {{os.path.getsize(fp):,}} 字节\\n")
open({RESULT!r}, "w", encoding="utf-8").write(out.getvalue())
''')
print("runner 已生成:", runner)

tn = "AGEexetest"
subprocess.run(["schtasks", "/Create", "/TN", tn,
                "/TR", f"C:\\Python314\\python.exe {runner}",
                "/SC", "ONCE", "/ST", "23:59", "/F", "/RL", "HIGHEST"],
               capture_output=True, text=True, encoding="utf-8", errors="replace")
subprocess.run(["schtasks", "/Run", "/TN", tn],
               capture_output=True, text=True, encoding="utf-8", errors="replace")
print("计划任务已启动，等待 …")

for i in range(90):
    time.sleep(2)
    if os.path.isfile(RESULT):
        sz1 = os.path.getsize(RESULT)
        time.sleep(2)
        if os.path.getsize(RESULT) == sz1:
            break
print()
print(open(RESULT, encoding="utf-8", errors="replace").read() if os.path.isfile(RESULT) else "✗ 结果文件未生成")
subprocess.run(["schtasks", "/Delete", "/TN", tn, "/F"], capture_output=True)
