import io, ast, re
p = "gui.py"
s = io.open(p, encoding="utf-8").read()
s2 = s.replace('APP_VER = "1.1"', 'APP_VER = "1.2"')
assert s2 != s, "no APP_VER replacement"
io.open(p, "w", encoding="utf-8", newline="\n").write(s2)
ast.parse(s2)
print("APP_VER 已改 1.2,", len(s2), "字符")
i = s2.index("APP_VER")
print(s2[max(0,i-120):i+80])
