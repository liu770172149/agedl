# -*- coding: utf-8 -*-
import io, os, subprocess, sys, time
out = io.StringIO()
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
cmd = ['D:\\deepseekproject\\agedl\\dist\\AGE下载器\\AGE下载器.exe', "--cli", "https://age001.com/play/12537-1-1.html",
       "-n", "1", "-f", "mp4", "-w", "24", "-o", 'D:\\迅雷下载\\video\\_exetest2']
t0 = time.time()
p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=1800, creationflags=CNW)
out.write(f"returncode={p.returncode} 用时={time.time()-t0:.1f}s\n")
out.write("--- stdout ---\n" + (p.stdout or "")[:2000] + "\n")
out.write("--- stderr ---\n" + (p.stderr or "")[:3000] + "\n")
log = os.path.join(os.path.dirname('D:\\deepseekproject\\agedl\\dist\\AGE下载器\\AGE下载器.exe'), "cli.log")
if os.path.isfile(log):
    out.write("--- cli.log ---\n" + open(log, encoding="utf-8", errors="replace").read()[-2500:] + "\n")
out.write("--- 产物 ---\n")
for root, _d, files in os.walk('D:\\迅雷下载\\video\\_exetest2'):
    for f in files:
        fp = os.path.join(root, f)
        out.write(f"  {f}  {os.path.getsize(fp):,} 字节\n")
open('D:\\deepseekproject\\agedl\\_exe_result.txt', "w", encoding="utf-8").write(out.getvalue())
