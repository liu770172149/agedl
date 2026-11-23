import discover as D
s = D.site_session()
det = D.fetch_detail(s, vid=12537)
it = det["item"]
print("名称:", it.name)
print("地区:", it.area, "| 语言:", it.lang, "| 年份:", it.year)
print("备注:", it.remarks, "| 标签:", it.tags)
print("更新:", it.updated)
print("播放页数:", len(det["plays"]))
print("前3:", det["plays"][:3])
print("--- kv ---")
for k, v in det["kvs"].items():
    print(f"  {k} = {v[:40]}")
