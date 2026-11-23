# -*- coding: utf-8 -*-
"""
discover.py —— AGE动漫 站点内容发现层（热门榜 / 最新更新 / 搜索）

不依赖 tkinter，可单独自测：
    python discover.py --selftest

数据来源（全部实测可用）：
    榜单页   https://www.age001.com/label/top.html    → 本周/本月/总 三个榜，各 25 条，含热度值
    新番页   https://www.age001.com/label/new.html    → 24 张卡片
    今日页   https://www.age001.com/label/today.html  → 24 张卡片
    首页更新 https://www.age001.com/                  → one_new_anime 列表，约 104 条 名称+更新至
    最新入库 https://www.age001.com/index.php/ajax/data?mid=1&limit=20&page=N
                                                      → JSON，共 28528 部，page 真实翻页，limit 上限 20
    搜索     https://www.age001.com/index.php/ajax/suggest?mid=1&wd=X&limit=100
                                                      → JSON，服务端真搜索，中文可用，不触发验证码
    详情页   https://www.age001.com/vod/<vid>.html     → 含全部 /play/ 播放页链接

注意：
    /index.php/ajax/data 会忽略 wd / tid / order 参数，它只是「按时间倒序的全站分页」。
    真正的搜索必须走 /index.php/ajax/suggest。
    /search/xxx.html 会触发 WAF 滑动验证码，不要用。
"""
from __future__ import annotations

import html as _html
import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

import requests

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
SITE = "https://www.age001.com"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

API_DATA = SITE + "/index.php/ajax/data"
API_SUGGEST = SITE + "/index.php/ajax/suggest"
URL_RANK = SITE + "/label/top.html"
URL_NEW = SITE + "/label/new.html"
URL_TODAY = SITE + "/label/today.html"
URL_HOME = SITE + "/"

# 榜单分组标题：<p class="dm-p">本周动画排行榜</p>
GROUP_RE = re.compile(r'<p class="dm-p">\s*([^<]+?)\s*</p>', re.S)

# 榜单条目
RANK_ITEM_RE = re.compile(
    r'<li class="rank_text">\s*'
    r'<span class="rank_text_idx[^"]*"[^>]*>\s*([^<]*?)\s*</span>\s*'
    r'<a\s+href="([^"]+)"[^>]*>\s*'
    r'<span class="rank_text_name"[^>]*>\s*([^<]*?)\s*</span>\s*'
    r'</a>\s*'
    r'<span class="rank_value[^"]*"[^>]*>\s*([^<]*?)\s*</span>',
    re.S,
)

# 卡片（anime_icon1 / anime_icon2 结构同构）
CARD_RE = re.compile(
    r'<li class="anime_icon[12]">\s*'
    r'<a\s+href="([^"]+)"[^>]*>\s*'
    r'<img[^>]*?data_src="([^"]*)"[^>]*?alt="([^"]*)"[^>]*?title="([^"]*)"[^>]*>\s*'
    r'<span class="anime_icon1_name1"[^>]*>\s*([^<]*?)\s*</span>',
    re.S,
)

# 首页「最新更新」：<li class="one_new_anime">
NEW_ITEM_RE = re.compile(
    r'<li class="one_new_anime">\s*'
    r'<a class="one_new_anime_name"\s+href="([^"]+)"[^>]*>\s*([^<]*?)\s*</a>\s*'
    r'<a class="one_new_anime_ji"\s+href="[^"]*"[^>]*>\s*([^<]*?)\s*</a>',
    re.S,
)

VOD_ID_RE = re.compile(r"/vod/(\d+)\.html")
PLAY_RE = re.compile(r'href="(/play/\d+-\d+-\d+\.html)"')
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)

# 详情页信息行：一条一个 <li class="detail_imform_kv">，键与值都在里面
# 形如 <li class="detail_imform_kv">
#        <span class="detail_imform_tag">发行地区：</span>
#        <span class="detail_imform_value">日本</span>
#        <a class="detail_imform_show_full" href="...">&lt;&lt;展开</a></li>
# 值里可能嵌 <a>（如 动画分类：<a href="/type/2.html">日韩动漫</a>），所以必须整块取再剥标签
KV_RE = re.compile(
    r'<li class="detail_imform_kv">\s*'
    r'<span class="detail_imform_tag"[^>]*>\s*(.*?)\s*</span>\s*'
    r'<span class="detail_imform_value"[^>]*>\s*(.*?)\s*</span>',
    re.S)
STRIP_TAG_RE = re.compile(r"<[^>]+>")

# 零宽字符（站点数据里带 \u200b，不清理会导致搜索比对失败）
ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)


def clean(s: str) -> str:
    """去掉零宽字符与多余空白。"""
    if not s:
        return ""
    return _html.unescape(s).translate(ZW).strip()


def _int(s, default: int = 0) -> int:
    try:
        return int(str(s).strip())
    except Exception:
        return default


# --------------------------------------------------------------------------- #
# 数据类
# --------------------------------------------------------------------------- #
@dataclass
class VodItem:
    """一部作品。字段按数据源可填多少填多少。"""
    vid: int = 0
    name: str = ""
    pic: str = ""
    year: str = ""
    area: str = ""
    lang: str = ""
    remarks: str = ""
    score: str = ""
    hits: int = 0
    hits_day: int = 0
    hits_week: int = 0
    hits_month: int = 0
    updated: str = ""
    blurb: str = ""
    tags: str = ""
    type_name: str = ""
    detail_url: str = ""
    rank: int = 0                    # 榜单名次；非榜单来源为 0

    @property
    def play_url(self) -> str:
        """按第一线路第一集猜一个播放页地址（详情页解析成功时以真实值为准）。"""
        return f"{SITE}/play/{self.vid}-1-1.html" if self.vid else ""

    @property
    def web_url(self) -> str:
        return self.detail_url or (f"{SITE}/vod/{self.vid}.html" if self.vid else "")


@dataclass
class RankEntry:
    """榜单中的一条。"""
    rank: int = 0
    name: str = ""
    value: int = 0
    detail_url: str = ""
    vid: int = 0
    group: str = ""


@dataclass
class RankBoard:
    """一个榜单分组（本周 / 本月 / 总）。"""
    group: str = ""
    entries: list = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def top_value(self) -> int:
        return max((e.value for e in self.entries), default=0)

    @property
    def avg_value(self) -> float:
        if not self.entries:
            return 0.0
        return sum(e.value for e in self.entries) / len(self.entries)


# --------------------------------------------------------------------------- #
# 会话
# --------------------------------------------------------------------------- #
def site_session(ua: str = DEFAULT_UA, timeout: int = 20) -> requests.Session:
    """建一个带站点常规头的会话，并先访问首页拿 cookie。"""
    s = requests.Session()
    s.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": SITE + "/",
    })
    try:
        s.get(SITE + "/", timeout=timeout)
    except Exception:
        pass
    return s


def _text(sess: requests.Session, url: str, timeout: int = 20, **kw) -> str:
    r = sess.get(url, timeout=timeout, **kw)
    r.raise_for_status()
    # 站点是 utf-8；个别页给 gbk 声明时才回退
    enc = r.encoding
    if not enc or enc.lower() in ("iso-8859-1", "ascii"):
        enc = "utf-8"
    r.encoding = enc
    return r.text


def _json(sess: requests.Session, url: str, params: dict, timeout: int = 25) -> dict:
    hdr = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*"}
    r = sess.get(url, params=params, headers=hdr, timeout=timeout)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------- #
# 解析：榜单
# --------------------------------------------------------------------------- #
def parse_rank_page(html: str) -> list:
    """把 /label/top.html 拆成若干 RankBoard。"""
    marks = [(m.start(), clean(m.group(1))) for m in GROUP_RE.finditer(html)]
    if not marks:
        # 没有分组标题时，全部当作一个「排行榜」
        marks = [(0, "排行榜")]
    boards = []
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(html)
        seg = html[pos:end]
        entries = []
        for m in RANK_ITEM_RE.finditer(seg):
            url = clean(m.group(2))
            vid_m = VOD_ID_RE.search(url)
            entries.append(RankEntry(
                rank=_int(clean(m.group(1))),
                name=clean(m.group(3)),
                value=_int(clean(m.group(4))),
                detail_url=url if url.startswith("http") else SITE + url,
                vid=_int(vid_m.group(1)) if vid_m else 0,
                group=name,
            ))
        if entries:
            boards.append(RankBoard(group=name, entries=entries))
    return boards


# --------------------------------------------------------------------------- #
# 解析：卡片列表 / 首页更新
# --------------------------------------------------------------------------- #
def parse_card_list(html: str) -> list:
    """解析 anime_icon1 / anime_icon2 卡片网格。"""
    out = []
    for m in CARD_RE.finditer(html):
        url = clean(m.group(1))
        vid_m = VOD_ID_RE.search(url)
        out.append(VodItem(
            vid=_int(vid_m.group(1)) if vid_m else 0,
            name=clean(m.group(3)),
            pic=clean(m.group(2)),
            remarks=clean(m.group(5)),
            detail_url=url if url.startswith("http") else SITE + url,
        ))
    return out


def parse_home_updates(html: str) -> list:
    """解析首页 one_new_anime 列表（名称 + 更新至第几集）。"""
    out = []
    for m in NEW_ITEM_RE.finditer(html):
        url = clean(m.group(1))
        vid_m = VOD_ID_RE.search(url)
        out.append(VodItem(
            vid=_int(vid_m.group(1)) if vid_m else 0,
            name=clean(m.group(2)),
            remarks=clean(m.group(3)),
            detail_url=url if url.startswith("http") else SITE + url,
        ))
    return out


# --------------------------------------------------------------------------- #
# 取数：榜单
# --------------------------------------------------------------------------- #
def fetch_rank(sess: Optional[requests.Session] = None) -> list:
    """取三个榜单（本周 / 本月 / 总）。"""
    s = sess or site_session()
    return parse_rank_page(_text(s, URL_RANK))


def fetch_cards(sess: Optional[requests.Session] = None,
                which: str = "new") -> list:
    """取新番（new）或今日更新（today）卡片。"""
    s = sess or site_session()
    url = URL_NEW if which == "new" else URL_TODAY
    return parse_card_list(_text(s, url))


def fetch_home_updates(sess: Optional[requests.Session] = None) -> list:
    """取首页「最新更新」列表。"""
    s = sess or site_session()
    return parse_home_updates(_text(s, URL_HOME))


# --------------------------------------------------------------------------- #
# 取数：最新入库（JSON 分页）
# --------------------------------------------------------------------------- #
def _item_from_api(d: dict) -> VodItem:
    t = d.get("type") or {}
    if isinstance(t, str):
        try:
            t = json.loads(t.replace("'", '"'))
        except Exception:
            t = {}
    return VodItem(
        vid=_int(d.get("vod_id")),
        name=clean(d.get("vod_name", "")),
        pic=clean(d.get("vod_pic", "")),
        year=clean(str(d.get("vod_year", ""))),
        area=clean(d.get("vod_area", "")),
        lang=clean(d.get("vod_lang", "")),
        remarks=clean(d.get("vod_remarks", "")),
        score=clean(str(d.get("vod_score", ""))),
        hits=_int(d.get("vod_hits")),
        hits_day=_int(d.get("vod_hits_day")),
        hits_week=_int(d.get("vod_hits_week")),
        hits_month=_int(d.get("vod_hits_month")),
        updated=clean(d.get("vod_time", "")),
        blurb=clean(d.get("vod_blurb", "")),
        tags=clean(d.get("vod_tag", "")),
        type_name=clean(t.get("type_name", "")) if isinstance(t, dict) else "",
        detail_url=SITE + (d.get("detail_link") or f"/vod/{d.get('vod_id')}.html"),
    )


def fetch_latest(sess: Optional[requests.Session] = None, page: int = 1,
                 limit: int = 20) -> dict:
    """取「最新入库」一页。

    返回 {"items": [...], "total": int, "pagecount": int, "page": int, "limit": int}
    注意：接口把 limit 上限锁在 20，传更大会退回 10。
    """
    s = sess or site_session()
    limit = max(1, min(int(limit), 20))
    j = _json(s, API_DATA, {"mid": 1, "tid": 1, "limit": limit, "page": max(1, int(page))})
    items = [_item_from_api(d) for d in (j.get("list") or [])]
    return {
        "items": items,
        "total": _int(j.get("total")),
        "pagecount": _int(j.get("pagecount")),
        "page": _int(j.get("page"), page),
        "limit": limit,
    }


# --------------------------------------------------------------------------- #
# 取数：搜索
# --------------------------------------------------------------------------- #
def search_vods(sess: Optional[requests.Session] = None, wd: str = "",
                limit: int = 100) -> dict:
    """服务端搜索（走 ajax/suggest，中文可用、无验证码）。

    返回 {"items": [...], "total": int, "wd": str}
    该接口只给 id / name / en / pic，其余字段留空，选中条目时可再拉详情页补全。
    """
    s = sess or site_session()
    wd = (wd or "").strip()
    if not wd:
        return {"items": [], "total": 0, "wd": wd}
    limit = max(1, min(int(limit), 200))
    j = _json(s, API_SUGGEST, {"mid": 1, "wd": wd, "limit": limit})
    items = []
    for d in (j.get("list") or []):
        items.append(VodItem(
            vid=_int(d.get("id")),
            name=clean(d.get("name", "")),
            pic=clean(d.get("pic", "")),
            detail_url=f"{SITE}/vod/{_int(d.get('id'))}.html",
        ))
    return {"items": items, "total": _int(j.get("total")), "wd": wd}


# --------------------------------------------------------------------------- #
# 详情：补全一部作品的信息与播放页
# --------------------------------------------------------------------------- #
def fetch_detail(sess: Optional[requests.Session] = None,
                 item: Optional[VodItem] = None, vid: int = 0) -> dict:
    """抓详情页，补全字段并取出全部 /play/ 播放页链接。

    返回 {"item": VodItem, "plays": [url...], "kvs": {标签: 值}}
    """
    s = sess or site_session()
    vid = vid or (item.vid if item else 0)
    it = item or VodItem(vid=vid)
    if not vid:
        return {"item": it, "plays": [], "kvs": {}}

    h = _text(s, f"{SITE}/vod/{vid}.html")
    it.detail_url = f"{SITE}/vod/{vid}.html"

    m = TITLE_RE.search(h)
    if m and not it.name:
        t = clean(m.group(1))
        t = re.sub(r"^《|》.*$", "", t)
        it.name = t

    plays = []
    for u in PLAY_RE.findall(h):
        full = u if u.startswith("http") else SITE + u
        if full not in plays:
            plays.append(full)

    # 一条 li 一个键值，值里可能嵌 <a>，统一剥标签
    kvs = {}
    for m in KV_RE.finditer(h):
        k = clean(STRIP_TAG_RE.sub("", m.group(1))).rstrip("：: ")
        v = clean(STRIP_TAG_RE.sub("", m.group(2)))
        if k and k not in kvs:
            kvs[k] = v

    # 常见字段回填（键名按包含关系匹配）
    for key, attr in (("发行地区", "area"), ("地区", "area"),
                      ("语言对白", "lang"), ("语言", "lang"),
                      ("发行时间", "year"), ("年份", "year"),
                      ("剧情类型", "tags"), ("类型", "tags"),
                      ("播放状态", "remarks"), ("上次更新", "updated")):
        for k, v in kvs.items():
            if key in k and not getattr(it, attr):
                setattr(it, attr, v)
                break

    if not it.pic:
        pics = re.findall(r'<img[^>]*data_src="([^"]+)"', h)
        if pics:
            it.pic = clean(pics[0])

    return {"item": it, "plays": plays, "kvs": kvs}


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #
SOURCES = [
    ("本周排行", "rank:本周"),
    ("本月排行", "rank:本月"),
    ("总排行", "rank:总"),
    ("最新入库", "latest"),
    ("今日更新", "today"),
    ("新番上架", "new"),
    ("首页更新", "home"),
]


def load_source(sess: requests.Session, key: str, page: int = 1) -> dict:
    """按数据源键取数，返回统一结构。

    返回 {"kind": "rank"|"list", "title": str, "boards": [...], "items": [...],
          "total": int, "page": int, "pagecount": int}
    """
    kind = key.split(":", 1)[0]
    if kind == "rank":
        want = key.split(":", 1)[1] if ":" in key else ""
        boards = fetch_rank(sess)
        if want:
            picked = [b for b in boards if want in b.group]
            boards = picked or boards
        all_entries = [e for b in boards for e in b.entries]
        items = [VodItem(vid=e.vid, name=e.name, detail_url=e.detail_url,
                         hits=e.value, remarks=f"第{e.rank}名", rank=e.rank)
                 for e in all_entries]
        title = " + ".join(b.group for b in boards) or "排行榜"
        return {"kind": "rank", "title": title, "boards": boards, "items": items,
                "total": len(items), "page": 1, "pagecount": 1}

    if kind == "latest":
        d = fetch_latest(sess, page=page, limit=20)
        return {"kind": "list", "title": "最新入库", "boards": [],
                "items": d["items"], "total": d["total"],
                "page": d["page"], "pagecount": d["pagecount"]}

    if kind in ("today", "new"):
        items = fetch_cards(sess, which=kind)
        return {"kind": "list", "title": "今日更新" if kind == "today" else "新番上架",
                "boards": [], "items": items, "total": len(items),
                "page": 1, "pagecount": 1}

    items = fetch_home_updates(sess)
    return {"kind": "list", "title": "首页更新", "boards": [], "items": items,
            "total": len(items), "page": 1, "pagecount": 1}


# --------------------------------------------------------------------------- #
# 自测
# --------------------------------------------------------------------------- #
def _selftest() -> None:
    out = []

    def p(s: str = "") -> None:
        out.append(s)
        if sys.stdout:
            print(s)

    t0 = time.time()
    s = site_session()
    p("=" * 74)
    p("榜单 /label/top.html")
    boards = fetch_rank(s)
    for b in boards:
        p(f"  {b.group}: {b.count} 条  最高热度 {b.top_value}  平均 {b.avg_value:.1f}")
        for e in b.entries[:3]:
            p(f"     #{e.rank:2} {e.name}  {e.value}  vid={e.vid}")
    p()
    p("新番 /label/new.html")
    cards = fetch_cards(s, "new")
    p(f"  {len(cards)} 条")
    for c in cards[:3]:
        p(f"     {c.name}  [{c.remarks}]  vid={c.vid}")
    p()
    p("今日 /label/today.html")
    cards = fetch_cards(s, "today")
    p(f"  {len(cards)} 条")
    for c in cards[:3]:
        p(f"     {c.name}  [{c.remarks}]  vid={c.vid}")
    p()
    p("首页更新")
    ups = fetch_home_updates(s)
    p(f"  {len(ups)} 条")
    for c in ups[:3]:
        p(f"     {c.name}  [{c.remarks}]  vid={c.vid}")
    p()
    p("最新入库 ajax/data page=1")
    d = fetch_latest(s, page=1)
    p(f"  total={d['total']} pagecount={d['pagecount']} 本页 {len(d['items'])} 条")
    for it in d["items"][:3]:
        p(f"     {it.name}  年份={it.year} 地区={it.area} 备注={it.remarks} "
          f"播放={it.hits} 类型={it.type_name}")
    p()
    p("搜索 命运")
    r = search_vods(s, "命运")
    p(f"  total={r['total']} 返回 {len(r['items'])} 条")
    for it in r["items"][:3]:
        p(f"     {it.name}  vid={it.vid}")
    if r["items"]:
        p()
        p("详情补全 第一部命中")
        det = fetch_detail(s, r["items"][0])
        p(f"  名称={det['item'].name}")
        p(f"  播放页 {len(det['plays'])} 个: {det['plays'][:3]}")
        p(f"  信息行: {list(det['kvs'].items())[:6]}")
    p()
    p(f"耗时 {time.time() - t0:.2f}s")
    p("=" * 74)

    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "discover_selftest.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    import os

    if "--selftest" in sys.argv or "-t" in sys.argv:
        _selftest()
    else:
        print(__doc__)
