import io
s = io.open("gui.py", encoding="utf-8").read()
for key in ("self._d_busy = False", "_d_detail_cache"):
    i = s.index(key)
    print(f"--- {key} ---")
    print(s[max(0,i-260):i+200])
