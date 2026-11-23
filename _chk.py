import ast, io, sys
p = "gui.py"
s = io.open(p, encoding="utf-8").read()
try:
    ast.parse(s)
    print("AST OK,", len(s), "chars")
except SyntaxError as e:
    print("SyntaxError line", e.lineno, ":", e.msg)
    lines = s.split("\n")
    for i in range(max(0, e.lineno-4), min(len(lines), e.lineno+3)):
        print(f"  {i+1}: {lines[i]}")
    sys.exit(1)
# 检查关键符号
for name in ["class App", "def _build_download_ui", "def _build_discover_ui",
             "def on_discover_load", "def on_discover_search",
             "def on_discover_to_download", "d_rows", "d_error", "d_idle"]:
    print(f"  {name}: {'OK' if name in s else 'MISSING'}")
