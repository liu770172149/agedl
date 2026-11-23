import io
s = io.open("gui.py", encoding="utf-8").read()
i = s.index("    def _drain")
j = s.index("    def _handle")
print(s[i:j])
print("=== _on_tab_changed ===")
a = s.index("    def _on_tab_changed")
b = s.index("    def _d_stat") if s.index("    def _d_stat") > a else a+900
print(s[a:a+900])
