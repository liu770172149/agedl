import io
s = io.open("core.py", encoding="utf-8").read()
for key in ("class JobOptions", "class Job:", "class Series", "class Episode", "class Probe"):
    i = s.index(key)
    print("="*20, key)
    print(s[i:i+1500])
    print()
