# -*- coding: utf-8 -*-
import io, os, subprocess, time
CNW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
buf = []
cmd = ['D:\\AGE下载器\\AGE下载器.exe', "--cli", "https://age001.com/play/12537-1-1.html",
       "-n", "1", "-f", "mp4", "-w", "24", "-o", 'D:\\迅雷下载\\video\\_exetest3']
t0 = time.time()
p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=1800, creationflags=CNW)
buf.append(f"returncode={p.returncode} 用时={time.time()-t0:.1f}s")
buf.append("--- stdout ---")
buf.append((p.stdout or "")[:2000])
buf.append("--- stderr ---")
buf.append((p.stderr or "")[:3000])
log = os.path.join(os.path.dirname('D:\\AGE下载器\\AGE下载器.exe'), "cli.log")
if os.path.isfile(log):
    buf.append("--- cli.log ---")
    buf.append(open(log, encoding="utf-8", errors="replace").read()[-2500:])
buf.append("--- 产物 ---")
for root, _d, files in os.walk('D:\\迅雷下载\\video\\_exetest3'):
    for f in files:
        fp = os.path.join(root, f)
        buf.append(f"  {f}  {os.path.getsize(fp):,} 字节")
open('D:\\deepseekproject\\agedl\\_exe_result3.txt', "w", encoding="utf-8").write("\n".join(buf))
