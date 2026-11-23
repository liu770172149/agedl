import sys, time
sys.path.insert(0, r"D:\deepseekproject\agedl")
import discover
s = discover.site_session()
for wd in ("命运", "斗破", "火影", "海贼"):
    t = time.time()
    r = discover.search_vods(s, wd, limit=200)
    print(f"{wd}: {len(r['items'])} 条 total={r['total']} 用时 {time.time()-t:.2f}s  首条={r['items'][0].name if r['items'] else '-'}")
