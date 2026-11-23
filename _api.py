import io, re
for f in ("core.py", "discover.py"):
    s = io.open(f, encoding="utf-8").read()
    print(f"===== {f} ({len(s)} 字符) =====")
    for m in re.finditer(r"^(?:def |class )(\w+)(\([^)]*\))?", s, re.M):
        sig = (m.group(2) or "").replace("\n", " ")
        print(f"  {m.group(1)}{sig}")
