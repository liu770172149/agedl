import io, ast
s = io.open("gui.py", encoding="utf-8").read()
ast.parse(s)
print("AST OK", len(s), "chars")
# 顺便查一遍所有线程体里是否还有 tk 变量直读
import re
bad = []
for m in re.finditer(r"def (work|_probe_all_worker|_d_worker|_load_source_async|_d_fetch_detail)[^\n]*:\n((?:[ \t]+.*\n)+)", s):
    name, body = m.group(1), m.group(2)
    for line in body.split("\n"):
        if re.search(r"self\.\w+_var\.get\(\)|self\.out_dir\.get\(\)", line):
            bad.append(f"{name}: {line.strip()}")
print("线程内 tk 变量直读:", bad if bad else "无")
