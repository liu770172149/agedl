import re, discover as D
s = D.site_session()
h = s.get("https://www.age001.com/vod/12537.html", timeout=20).text
i = h.find("detail_imform")
print("idx:", i, "len:", len(h))
print(h[i-200:i+2600])
