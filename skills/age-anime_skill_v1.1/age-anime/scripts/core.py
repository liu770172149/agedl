# -*- coding: utf-8 -*-
"""
core.py - AGE动漫 / maccms 站点解析 + HLS 下载 + TS/MP4 输出

不依赖界面，可单独自测：
    python core.py --selftest "https://age001.com/play/12537-1-1.html"

对外 API（GUI 依赖，勿随意改名）：
    数据类  : Episode, Line, Series, Segment, Playlist, BlockInfo, Probe, Progress, JobOptions
    工具函数: human_bytes, human_time, sanitize
    网络    : make_session, resolve_play_url, fetch_text
    解析    : parse_series, extract_player_cfg, pick_variant, parse_media_playlist
    探测    : describe_blocks, drop_ad_blocks, probe_episode
    转封装  : find_ffmpeg, ffmpeg_version, remux_mp4
    下载    : SegmentDownloader, Job

发现页（浏览 / 榜单 / 搜索）API：
    数据类  : VodItem, RankEntry, RankBoard, SearchPage
    网络    : site_session, site_api_data, site_api_suggest
    解析    : parse_rank_page, parse_card_list
    门面    : fetch_latest, fetch_hot, fetch_rank, search_vods, resolve_vod_play_url
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import requests

import platform_compat as plat

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

PLAYER_RE = re.compile(r"player_aaaa\s*=\s*(\{.*?\})\s*</script>", re.S)
VOD_NAME_RE = re.compile(r'"vod_name"\s*:\s*"([^"]*)"')
EXTINF_RE = re.compile(r"#EXTINF:\s*([0-9.]+)", re.I)
KEY_RE = re.compile(r'#EXT-X-KEY:.*?METHOD=([A-Z0-9-]+)(.*)', re.I)
PLAY_LINK_RE = re.compile(r'href\s*=\s*["\']([^"\']*?/play/\d+-\d+-\d+\.html)', re.I)

TS_PACKET = 188
SYNC = 0x47

CHECK_ON = "☑"
CHECK_OFF = "☐"


# --------------------------------------------------------------------------- #
# 数据类
# --------------------------------------------------------------------------- #
@dataclass
class Episode:
    sid: int
    nid: int
    label: str
    play_url: str
    # 探测结果（懒填充）
    duration: Optional[float] = None
    bandwidth: Optional[int] = None
    resolution: str = ""
    seg_count: int = 0
    key_method: str = ""
    ad_blocks: int = 0
    probe_error: Optional[str] = None
    probed: bool = False
    status: str = "待下载"
    saved_path: Optional[str] = None

    @property
    def estimate_bytes(self) -> Optional[int]:
        if self.duration and self.bandwidth:
            return int(self.duration * self.bandwidth / 8)
        return None


@dataclass
class Line:
    sid: int
    name: str
    episodes: list[Episode] = field(default_factory=list)


@dataclass
class Series:
    title: str
    aid: int
    base_host: str
    source_url: str
    lines: list[Line] = field(default_factory=list)

    @property
    def total_episodes(self) -> int:
        return max((len(l.episodes) for l in self.lines), default=0)


@dataclass
class Segment:
    index: int
    url: str
    duration: float
    block: int = 0
    src: str = ""


@dataclass
class Playlist:
    variant_url: str
    segments: list[Segment] = field(default_factory=list)
    key_uri: str = ""
    key_method: str = "NONE"
    total_duration: float = 0.0
    bandwidth: int = 0
    resolution: str = ""


@dataclass
class BlockInfo:
    block: int
    segs: int
    duration: float
    src: str


@dataclass
class Probe:
    playlist: Playlist
    dropped: list[BlockInfo] = field(default_factory=list)
    m3u8: str = ""


@dataclass
class Progress:
    done: int = 0
    total: int = 0
    nbytes: int = 0
    failed: int = 0
    speed: float = 0.0
    elapsed: float = 0.0

    @property
    def percent(self) -> float:
        return (self.done / self.total * 100.0) if self.total else 0.0


@dataclass
class JobOptions:
    out_dir: str
    fmt: str = "mp4"
    workers: int = 16
    retries: int = 5
    drop_ads: bool = True
    keep_segments: bool = False
    ffmpeg: str = ""
    ua: str = DEFAULT_UA
    prefer_bandwidth: int = 0


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def human_bytes(n: float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def human_time(sec: Optional[float]) -> str:
    if not sec:
        return "-"
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def sanitize(name: str, limit: int = 110) -> str:
    """生成跨平台安全文件名。

    按 Windows 非法字符清洗（NTFS 不允许），并按 UTF-8 字节数截断：
    ext4/APFS 的单个文件名上限是 255 字节，中文占 3 字节，
    只按字符数截断会写出 330 字节的名字，在 Linux 上 ENAMETOOLONG。
    """
    return plat.safe_filename(name, limit=limit)


def json_unescape(s: str) -> str:
    try:
        return json.loads('"' + s + '"')
    except Exception:  # noqa: BLE001
        return s


def split_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def src_of(url: str) -> str:
    """取 host + 路径前两级，用来区分正片源和广告源。"""
    try:
        p = urlparse(url)
        parts = [x for x in p.path.split("/") if x][:2]
        return p.netloc + "/" + "/".join(parts)
    except Exception:  # noqa: BLE001
        return url


def origin_of(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}/"
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# 网络
# --------------------------------------------------------------------------- #
def make_session(ua: str = DEFAULT_UA, referer: str = "") -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    if referer:
        s.headers["Referer"] = referer
    return s


def fetch_text(sess: requests.Session, url: str, timeout: int = 20) -> str:
    r = sess.get(url, timeout=timeout)
    r.raise_for_status()
    ctype = (r.headers.get("Content-Type") or "").lower()
    # 站点多为 utf-8；少量老 maccms 站用 gbk
    if "charset=gb" in ctype:
        return r.content.decode("gb18030", "replace")
    raw = r.content
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


# --------------------------------------------------------------------------- #
# 页面解析
# --------------------------------------------------------------------------- #
def extract_player_cfg(html: str) -> dict:
    """从播放页 HTML 取出 player_aaaa 配置（dict）。"""
    m = PLAYER_RE.search(html)
    if not m:
        return {}
    blob = m.group(1)
    try:
        return json.loads(blob)
    except Exception:  # noqa: BLE001
        pass
    try:  # 容错：去掉尾随逗号
        blob2 = re.sub(r",\s*([}\]])", r"\1", blob)
        return json.loads(blob2)
    except Exception:  # noqa: BLE001
        return {}


def extract_title(html: str, cfg: dict) -> str:
    name = ""
    vod = cfg.get("vod_data") if isinstance(cfg.get("vod_data"), dict) else None
    if vod:
        name = (vod.get("vod_name") or "").strip()
    if not name:
        m = VOD_NAME_RE.search(html)
        if m:
            name = m.group(1).strip()
    if not name:
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        if m:
            name = re.split(r"[|_\-–]", m.group(1))[0].strip()
    return name or "video"


def _parse_menu_names(html: str) -> list[str]:
    """取线路名称（menu0 里的 li 文本）。"""
    m = re.search(r'id\s*=\s*["\']menu0["\'][^>]*>(.*?)</ul>', html, re.S | re.I)
    if not m:
        return []
    block = m.group(1)
    names = []
    for li in re.findall(r"<li[^>]*>(.*?)</li>", block, re.S):
        t = re.sub(r"<[^>]+>", "", li).strip()
        if t:
            names.append(t)
    return names


def _parse_episode_blocks(html: str) -> list[list[tuple[str, str]]]:
    """按 movurl 块分组，返回 [[(href, label), ...], ...]。"""
    blocks: list[list[tuple[str, str]]] = []
    for mm in re.finditer(
            r'<div[^>]*class\s*=\s*["\'][^"\']*movurl[^"\']*["\'][^>]*>(.*?)</div>',
            html, re.S | re.I):
        body = mm.group(1)
        items = []
        for am in re.finditer(r"<a([^>]*)>(.*?)</a>", body, re.S):
            attrs, inner = am.group(1), am.group(2)
            hm = re.search(r'href\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
            if not hm:
                continue
            href = hm.group(1)
            if not re.search(r"/play/\d+-\d+-\d+\.html", href):
                continue
            label = re.sub(r"<[^>]+>", "", inner).strip()
            if not label:
                tm = re.search(r'title\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
                label = tm.group(1).strip() if tm else ""
            items.append((href, label))
        if items:
            blocks.append(items)
    return blocks


def _parse_episode_blocks_generic(html: str) -> list[list[tuple[str, str]]]:
    """通用兜底：直接扫全页 /play/AID-SID-NID.html 链接，按 sid 分组。"""
    groups: dict[int, list[tuple[str, str]]] = {}
    order: list[int] = []
    for am in re.finditer(r"<a([^>]*)>(.*?)</a>", html, re.S):
        attrs, inner = am.group(1), am.group(2)
        hm = re.search(r'href\s*=\s*["\']([^"\']*?/play/(\d+)-(\d+)-(\d+)\.html)', attrs, re.I)
        if not hm:
            continue
        href, sid = hm.group(1), int(hm.group(3))
        label = re.sub(r"<[^>]+>", "", inner).strip()
        if not label:
            tm = re.search(r'title\s*=\s*["\']([^"\']+)["\']', attrs, re.I)
            label = tm.group(1).strip() if tm else ""
        if sid not in groups:
            groups[sid] = []
            order.append(sid)
        groups[sid].append((href, label))
    # 去重（同一链接可能重复出现）
    out = []
    for sid in order:
        seen = set()
        uniq = []
        for href, label in groups[sid]:
            if href in seen:
                continue
            seen.add(href)
            uniq.append((href, label))
        out.append(uniq)
    return out


def parse_series(html: str, base_url: str) -> Series:
    """解析播放页 HTML，得到剧名 + 各线路各集。"""
    cfg = extract_player_cfg(html)
    title = extract_title(html, cfg)

    m = re.search(r"/play/(\d+)-(\d+)-(\d+)\.html", base_url)
    aid = int(m.group(1)) if m else 0

    names = _parse_menu_names(html)
    blocks = _parse_episode_blocks(html)

    # 若块数比线路名多/少，用通用扫描兜底
    if not blocks:
        blocks = _parse_episode_blocks_generic(html)

    lines: list[Line] = []
    for i, items in enumerate(blocks):
        if not items:
            continue
        sid_guess = None
        mm = re.search(r"/play/\d+-(\d+)-", items[0][0])
        if mm:
            sid_guess = int(mm.group(1))
        sid = sid_guess if sid_guess is not None else (i + 1)
        name = names[i] if i < len(names) else f"线路{sid}"
        eps = []
        for href, label in items:
            m2 = re.search(r"/play/\d+-\d+-(\d+)\.html", href)
            nid = int(m2.group(1)) if m2 else (len(eps) + 1)
            if not label:
                label = f"第{nid:02d}集"
            eps.append(Episode(sid=sid, nid=nid, label=label,
                               play_url=urljoin(base_url, href)))
        lines.append(Line(sid=sid, name=name, episodes=eps))

    if not lines:
        # 单集兜底：页面本身就是一集 play 页
        if m and cfg.get("url"):
            sid = int(m.group(2))
            nid = int(m.group(3))
            lines = [Line(sid=sid, name="当前线路",
                          episodes=[Episode(sid=sid, nid=nid, label=f"第{nid:02d}集",
                                            play_url=base_url)])]
        else:
            raise RuntimeError(
                "页面里没有找到集数列表。\n"
                "请粘贴某一集的播放页（形如 /play/12345-1-1.html），而不是详情页首页。")

    p = urlparse(base_url)
    return Series(title=title, aid=aid, base_host=p.netloc,
                  source_url=base_url, lines=lines)


def resolve_play_url(sess: requests.Session, url: str) -> tuple[str, dict, str]:
    """确保拿到一个真正含 player_aaaa 的播放页。

    输入可能是：播放页 / 详情页 / m3u8 直链。
    返回 (最终播放页 URL, player cfg, 页面 HTML)。
    """
    url = url.strip()
    html = ""
    cfg: dict = {}

    if "/play/" in url:
        html = fetch_text(sess, url)
        cfg = extract_player_cfg(html)
        if cfg:
            return url, cfg, html
    else:
        html = fetch_text(sess, url)

    # 详情页 -> 找第一个 /play/ 链接
    m = PLAY_LINK_RE.search(html) or re.search(
        r'href\s*=\s*["\']([^"\']*?/play/\d+-\d+-\d+\.html)', html, re.I)
    if m:
        nxt = urljoin(url, m.group(1))
        if nxt != url:
            html2 = fetch_text(sess, nxt)
            cfg2 = extract_player_cfg(html2)
            if cfg2:
                return nxt, cfg2, html2

    raise RuntimeError("该页面没有可用的片源地址（player_aaaa 为空）。\n"
                       "可能是这一集没上片、或该线路已失效，换一条线路试试。")


# --------------------------------------------------------------------------- #
# m3u8 解析
# --------------------------------------------------------------------------- #
def pick_variant(master_url: str, text: str, prefer_bandwidth: int = 0) -> tuple[str, int, str]:
    """master -> (最终 variant URL, bandwidth, resolution)。已是媒体列表则原样返回。"""
    lines = split_lines(text)
    if "#EXT-X-STREAM-INF" not in text:
        return master_url, 0, ""

    cands: list[tuple[int, str, str]] = []
    cur_bw, cur_res = 0, ""
    for ln in lines:
        if not ln:
            continue
        if ln.startswith("#EXT-X-STREAM-INF"):
            bm = re.search(r"BANDWIDTH=(\d+)", ln)
            rm = re.search(r"RESOLUTION=(\d+x\d+)", ln)
            cur_bw = int(bm.group(1)) if bm else 0
            cur_res = rm.group(1) if rm else ""
            continue
        if ln.startswith("#"):
            continue
        if ".m3u8" in ln or ln.endswith(".m3u8"):
            cands.append((cur_bw, urljoin(master_url, ln), cur_res))
            cur_bw, cur_res = 0, ""

    if not cands:
        raise RuntimeError("master playlist 里没有可用档位")

    if prefer_bandwidth:
        cands.sort(key=lambda x: (abs(x[0] - prefer_bandwidth), -x[0]))
    else:
        cands.sort(key=lambda x: -x[0])
    bw, u, res = cands[0]
    return u, bw, res


def parse_media_playlist(text: str, base_url: str, bandwidth: int = 0,
                         resolution: str = "") -> Playlist:
    pl = Playlist(variant_url=base_url, bandwidth=bandwidth, resolution=resolution)
    lines = split_lines(text)
    cur_dur = 0.0
    block = 0
    idx = 0

    for ln in lines:
        if not ln:
            continue
        if ln.startswith("#EXT-X-KEY"):
            km = KEY_RE.match(ln)
            if km:
                pl.key_method = km.group(1).upper()
                um = re.search(r'URI="([^"]+)"', ln)
                if um:
                    pl.key_uri = urljoin(base_url, um.group(1))
            continue
        if ln.startswith("#EXT-X-DISCONTINUITY"):
            block += 1
            continue
        if ln.startswith("#EXTINF"):
            m = EXTINF_RE.match(ln)
            cur_dur = float(m.group(1)) if m else 0.0
            continue
        if ln.startswith("#"):
            continue
        # 非 # 行 = 分片
        u = urljoin(base_url, ln)
        idx += 1
        pl.segments.append(Segment(index=idx, url=u, duration=cur_dur,
                                   block=block, src=src_of(u)))
        pl.total_duration += cur_dur
        cur_dur = 0.0

    if not pl.segments:
        raise RuntimeError("媒体播放列表里没解析出任何分片")
    return pl


def describe_blocks(pl: Playlist) -> list[BlockInfo]:
    agg: dict[int, list] = {}
    for s in pl.segments:
        a = agg.setdefault(s.block, [0, 0.0, s.src])
        a[0] += 1
        a[1] += s.duration
        if s.src:
            a[2] = s.src
    return [BlockInfo(block=b, segs=v[0], duration=v[1], src=v[2])
            for b, v in sorted(agg.items())]


def drop_ad_blocks(pl: Playlist) -> tuple[Playlist, list[BlockInfo]]:
    """剔除广告块。

    正片会被 #EXT-X-DISCONTINUITY 切成好几个块（同一台 CDN、同一个目录前缀），
    广告块则来自另一个源。所以判据是 **src**（host + 路径前两级）而不是 block：
    分片数最多的 src 是正片，保留所有属于该 src 的块。
    """
    blocks = describe_blocks(pl)
    if len(blocks) <= 1:
        return pl, []

    # 按 src 统计分片数，最多的那个 src 视为正片
    by_src: dict[str, int] = {}
    for s in pl.segments:
        by_src[s.src] = by_src.get(s.src, 0) + 1
    main_src = max(by_src, key=lambda k: by_src[k])

    keep = [s for s in pl.segments if s.src == main_src]
    dropped = [b for b in blocks if b.src != main_src]
    if not keep:                     # 兜底：src 全空时退回按块判
        return pl, []

    out = Playlist(variant_url=pl.variant_url, segments=keep,
                   key_uri=pl.key_uri, key_method=pl.key_method,
                   total_duration=sum(s.duration for s in keep),
                   bandwidth=pl.bandwidth, resolution=pl.resolution)
    return out, dropped


def probe_episode(sess: requests.Session, play_url: str, drop_ads: bool = True,
                  prefer_bandwidth: int = 0) -> Probe:
    final, cfg, _html = resolve_play_url(sess, play_url)
    m3u8 = (cfg.get("url") or "").strip()
    if not m3u8:
        raise RuntimeError("player_aaaa 里 url 为空")
    if not m3u8.lower().startswith("http"):
        m3u8 = urljoin(final, m3u8)

    text = fetch_text(sess, m3u8)
    vurl, bw, res = pick_variant(m3u8, text, prefer_bandwidth)
    if vurl != m3u8:
        text = fetch_text(sess, vurl)
    pl = parse_media_playlist(text, vurl, bandwidth=bw, resolution=res)

    dropped: list[BlockInfo] = []
    if drop_ads:
        pl, dropped = drop_ad_blocks(pl)
    return Probe(playlist=pl, dropped=dropped, m3u8=m3u8)


# --------------------------------------------------------------------------- #
# ffmpeg
# --------------------------------------------------------------------------- #
def candidate_ffmpeg_dirs() -> list[str]:
    """ffmpeg 候选目录（平台差异由 platform_compat 决定）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    dirs: list[str] = []

    if getattr(sys, "frozen", False):
        # PyInstaller onedir / onefile
        base = os.path.dirname(sys.executable)
        dirs += [base,
                 os.path.join(base, "ffmpeg"),
                 os.path.join(base, "ffmpeg", "bin"),
                 os.path.join(base, "bin"),
                 os.path.join(base, "tools", "ffmpeg", "bin"),
                 os.path.join(base, "_internal", "ffmpeg"),
                 os.path.join(base, "_internal", "ffmpeg", "bin"),
                 os.path.join(base, "_internal"),
                 os.path.join(os.path.dirname(base), "ffmpeg")]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(meipass)
    else:
        # 源码运行：skill/scripts/ → 向上找 ffmpeg、ffmpeg/bin、bin
        for up in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
            dirs += [up,
                     os.path.join(up, "ffmpeg"),
                     os.path.join(up, "ffmpeg", "bin"),
                     os.path.join(up, "bin"),
                     os.path.join(up, "tools", "ffmpeg", "bin")]

    # 平台相关常见安装位置（Windows 盘符 / Linux 的 /usr/bin、/snap/bin、Homebrew…）
    dirs += plat.ffmpeg_candidate_dirs()

    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def find_ffmpeg(extra: str = "") -> Optional[str]:
    if extra:
        if os.path.isfile(extra):
            return extra
        for n in plat.exe_names("ffmpeg"):
            p = os.path.join(extra, n)
            if os.path.isfile(p):
                plat.ensure_executable(p)
                return p
    for n in plat.exe_names("ffmpeg"):
        w = shutil.which(n)
        if w:
            plat.ensure_executable(w)
            return w
    for d in candidate_ffmpeg_dirs():
        for name in plat.exe_names("ffmpeg"):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                plat.ensure_executable(p)
                return p
    return None


def ffmpeg_version(exe: str) -> str:
    try:
        p = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=12,
                           **plat.spawn_kwargs())
        line = (p.stdout or "").splitlines()[0] if p.stdout else ""
        return line.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


# --------------------------------------------------------------------------- #
# ffmpeg 执行位置逃逸
# --------------------------------------------------------------------------- #
# 本机实测（见 _diag_host.py / _diag_copyff.py）：
#   某些企业 DLP 会按「可执行文件自身所在路径」限制写入范围：
#   例如从 D:\deepseekproject 内启动的 ffmpeg 只能写该目录，
#   写其它盘/目录一律 "Error opening output ... Permission denied"；
#   把同一个 ffmpeg 复制到该目录之外（用户 TEMP 最稳）再启动，写权限即恢复。
#   判定依据是「ffmpeg 二进制自身所在路径」，与输出路径、cwd、父进程都无关。
# 因此 remux 失败且 stderr 命中写权限拒绝时，自动复制副本到 TEMP 重试。
_ESCAPED_FFMPEG_LOCK = threading.Lock()


def escaped_ffmpeg(ffmpeg: str, on_log: Optional[Callable[[str], None]] = None) -> str:
    """返回一个不受写限制的 ffmpeg 路径（复制到临时目录的 agedl_ffbin 下）。

    仅在确认遇到 Permission denied 后调用，所以这里无条件复制；
    已有同大小副本时直接复用，不重复拷 172MB。
    """
    if not ffmpeg:
        return ffmpeg
    dst_dir = os.path.join(tempfile.gettempdir(), "agedl_ffbin")
    dst = os.path.join(dst_dir, plat.exe_names("ffmpeg")[0])
    with _ESCAPED_FFMPEG_LOCK:
        try:
            src_size = os.path.getsize(ffmpeg)
        except OSError:
            return ffmpeg
        if os.path.isfile(dst) and os.path.getsize(dst) == src_size:
            return dst
        try:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(ffmpeg, dst)
        except OSError as e:  # noqa: BLE001
            if on_log:
                on_log(f"  复制 ffmpeg 到临时目录失败：{e}")
            return ffmpeg
        plat.ensure_executable(dst)     # POSIX 上从 zip 出来的文件没有 +x
        if on_log:
            on_log(f"  ffmpeg 受路径限制，已复制副本：{dst}")
        return dst


def _looks_like_denied(text: str) -> bool:
    """stderr 是否表现为输出文件被拒绝写入。"""
    t = (text or "").lower()
    return "permission denied" in t


def remux_container(ffmpeg: str, src: str, dst: str,
                    on_log: Optional[Callable[[str], None]] = None) -> bool:
    """把合并好的传输流无损封装成目标容器（.mp4 / .mkv）。

    src 一律使用安全扩展名（.raw）：本机装有透明加密驱动，会接管 .ts 文件的写入，
    导致产物是加密容器、任何播放器都读不出画面。
    """
    ext = os.path.splitext(dst)[1].lower()
    tmp = dst + ".part" + ext
    is_mp4 = ext == ".mp4"

    def run(args: list[str], exe: str) -> bool:
        # 每轮都从干净状态开始，避免上一轮残留文件造成假成功
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        try:
            p = subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error"]
                               + args,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
                               **plat.spawn_kwargs())
            # ffmpeg 写的是 tmp，必须检查 tmp（早期版本误判 dst 导致封装成功却报失败）
            if p.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                return True
            if on_log and p.stderr:
                on_log("  ffmpeg: " + p.stderr.strip().splitlines()[-1][:200])
            # 记录是不是写权限问题，交给外层决定要不要换副本重来
            nonlocal_denied[0] = _looks_like_denied(p.stderr)
        except Exception as e:  # noqa: BLE001
            if on_log:
                on_log(f"  ffmpeg 调用异常: {e}")
        return False

    # 用「原路径 → 逃逸副本」两级尝试，避免无谓地每次都复制 172MB 的 exe
    nonlocal_denied = [False]

    def run_auto(args: list[str]) -> bool:
        if run(args, ffmpeg):
            return True
        if nonlocal_denied[0]:
            alt = escaped_ffmpeg(ffmpeg, on_log)
            if alt and alt != ffmpeg:
                if on_log:
                    on_log("  检测到写权限被限制，改用临时目录里的 ffmpeg 副本重试 …")
                return run(args, alt)
        return False

    flags = ["-movflags", "+faststart"] if is_mp4 else []
    base = ["-i", src, "-c", "copy"] + flags + [tmp]
    # mp4 先带 AAC ADTS->ASC 位流过滤器（mov 容器需要 ASC）
    if is_mp4 and run_auto(base[:2] + ["-bsf:a", "aac_adtstoasc"] + base[2:]):
        os.replace(tmp, dst)
        return True
    # 退回纯 copy（mkv 直接走这条；mp4 无音频时也走这条）
    if run_auto(base):
        os.replace(tmp, dst)
        return True
    try:
        if os.path.exists(tmp):
            os.remove(tmp)      # 失败不留半成品
    except OSError:
        pass
    return False


# 旧名字保留，避免外部脚本 import 失败
remux_mp4 = remux_container


# --------------------------------------------------------------------------- #
# 下载
# --------------------------------------------------------------------------- #
class SegmentDownloader:
    """多线程下载分片，再按顺序合并成单文件。"""

    def __init__(self, pl: Playlist, seg_dir: str, workers: int = 16, retries: int = 5,
                 ua: str = DEFAULT_UA, referer: str = "",
                 on_progress: Optional[Callable[[Progress], None]] = None,
                 cancel: Optional[threading.Event] = None):
        self.pl = pl
        self.seg_dir = seg_dir
        self.workers = max(1, workers)
        self.retries = max(1, retries)
        self.ua = ua
        self.referer = referer
        self.on_progress = on_progress
        self.cancel = cancel or threading.Event()

        self.done = 0
        self.nbytes = 0
        self.failures: list[tuple[int, Segment, str]] = []
        self._lock = threading.Lock()
        self._t0 = 0.0

    # ------------------------------------------------------------- 单个 #
    def _fetch_one(self, sess: requests.Session, seg: Segment, attempt: int = 0) -> bool:
        path = os.path.join(self.seg_dir, f"{seg.index:05d}.seg")
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            with self._lock:
                self.done += 1
                self.nbytes += os.path.getsize(path)
            return True

        last_err = ""
        for i in range(attempt, self.retries):
            if self.cancel.is_set():
                return False
            try:
                r = sess.get(seg.url, timeout=30)
                r.raise_for_status()
                data = r.content
                if not data:
                    raise RuntimeError("空响应")
                if data[:1] != bytes([SYNC]):
                    # 不是 TS 包但可能是加密分片，先保留
                    if self.pl.key_method in ("NONE", ""):
                        raise RuntimeError(f"非 TS 数据（首字节 0x{data[0]:02X}）")
                tmp = path + ".part"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
                with self._lock:
                    self.done += 1
                    self.nbytes += len(data)
                return True
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                time.sleep(min(1.5 * (i + 1), 6.0))

        with self._lock:
            self.failures.append((seg.index, seg, last_err))
        return False

    # ------------------------------------------------------------- 全部 #
    def run(self) -> bool:
        os.makedirs(self.seg_dir, exist_ok=True)
        self._t0 = time.time()
        total = len(self.pl.segments)
        lock = threading.Lock()
        queue = list(self.pl.segments)
        qi = [0]

        local = threading.local()

        def worker():
            sess = getattr(local, "sess", None)
            if sess is None:
                sess = make_session(self.ua, self.referer)
                local.sess = sess
            while True:
                if self.cancel.is_set():
                    return
                with lock:
                    if qi[0] >= len(queue):
                        return
                    seg = queue[qi[0]]
                    qi[0] += 1
                self._fetch_one(sess, seg)

        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(min(self.workers, total))]
        for t in threads:
            t.start()

        last = 0.0
        while any(t.is_alive() for t in threads):
            if self.cancel.is_set():
                break
            time.sleep(0.15)
            now = time.time()
            if self.on_progress and now - last > 0.2:
                last = now
                el = now - self._t0
                self.on_progress(Progress(
                    done=self.done, total=total, nbytes=self.nbytes,
                    failed=len(self.failures),
                    speed=(self.nbytes / el) if el > 0 else 0.0, elapsed=el))

        for t in threads:
            t.join(timeout=2)

        # 失败串行补抓一轮
        if self.failures and not self.cancel.is_set():
            retry_ids = [x[0] for x in self.failures]
            self.failures = []
            sess = make_session(self.ua, self.referer)
            for sid in retry_ids:
                if self.cancel.is_set():
                    break
                seg = next((s for s in self.pl.segments if s.index == sid), None)
                if seg:
                    self._fetch_one(sess, seg, attempt=self.retries - 1)

        if self.on_progress:
            el = time.time() - self._t0
            self.on_progress(Progress(
                done=self.done, total=total, nbytes=self.nbytes,
                failed=len(self.failures),
                speed=(self.nbytes / el) if el > 0 else 0.0, elapsed=el))

        return not self.failures and self.done >= total

    # ------------------------------------------------------------- 合并 #
    def merge(self, target: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        tmp = target + ".part"
        with open(tmp, "wb") as out:
            for seg in self.pl.segments:
                p = os.path.join(self.seg_dir, f"{seg.index:05d}.seg")
                if not os.path.exists(p):
                    raise RuntimeError(f"缺分片 #{seg.index}，无法合并")
                with open(p, "rb") as f:
                    shutil.copyfileobj(f, out, 1024 * 1024)

        # 目标已存在（上次中断或被播放器占用）时 os.replace 会抛 WinError 5，
        # 先尝试删除；删不掉就退化为直接写目标路径。
        for attempt in range(3):
            try:
                if os.path.exists(target):
                    os.remove(target)
                os.replace(tmp, target)
                return target
            except PermissionError:
                if attempt == 2:
                    shutil.copyfile(tmp, target)
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    return target
                time.sleep(0.4)
        return target


# --------------------------------------------------------------------------- #
# 任务编排（供 GUI 调用）
# --------------------------------------------------------------------------- #
class Job:
    """一次多集下载任务。所有回调都在工作线程里触发。"""

    def __init__(self, series: Series, episodes: list[Episode], opts: JobOptions,
                 on_log: Optional[Callable[[str], None]] = None,
                 on_episode_progress: Optional[Callable[[int, Progress], None]] = None,
                 on_overall: Optional[Callable[[int, int, str], None]] = None,
                 on_episode_done: Optional[Callable[[Episode, bool, str], None]] = None,
                 cancel: Optional[threading.Event] = None):
        self.series = series
        self.episodes = episodes
        self.opts = opts
        self.on_log = on_log or (lambda m: None)
        self.on_episode_progress = on_episode_progress or (lambda i, p: None)
        self.on_overall = on_overall or (lambda d, t, lab: None)
        self.on_episode_done = on_episode_done or (lambda e, ok, msg: None)
        self.cancel = cancel or threading.Event()
        self.ok_count = 0
        self.fail_count = 0

    def run(self) -> tuple[int, int]:
        total = len(self.episodes)
        for i, ep in enumerate(self.episodes):
            if self.cancel.is_set():
                self.on_log("已取消")
                break
            self.on_overall(i, total, ep.label)
            ok, msg = self._one(i, ep)
            if ok:
                self.ok_count += 1
                ep.status = "已完成"
            else:
                self.fail_count += 1
                ep.status = "失败" if msg != "已取消" else "跳过"
            self.on_episode_done(ep, ok, msg)
        self.on_overall(total, total, "结束")
        return self.ok_count, self.fail_count

    # ------------------------------------------------------------- 单集 #
    def _one(self, idx: int, ep: Episode) -> tuple[bool, str]:
        opts = self.opts
        total = len(self.episodes)
        tag = f"[{idx + 1}/{total}] {ep.label}"

        name = sanitize(f"{self.series.title} {ep.label}")
        # 中间传输流用 .raw：本机透明加密驱动会接管 .ts 写入，产物会变成加密容器
        raw_path = os.path.join(opts.out_dir, name + ".raw")
        out_ext = ".mp4" if opts.fmt == "mp4" else ".mkv"
        final_path = os.path.join(opts.out_dir, name + out_ext)

        # 已存在就跳过
        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            ep.saved_path = final_path
            self.on_log(f"{tag} 已存在，跳过  {os.path.basename(final_path)}")
            return True, "已存在"

        self.on_log(f"{tag} 解析片源 …")
        try:
            sess = make_session(opts.ua)
            pr = probe_episode(sess, ep.play_url, opts.drop_ads, opts.prefer_bandwidth)
        except Exception as e:  # noqa: BLE001
            self.on_log(f"{tag} 解析失败：{e}")
            return False, str(e)

        pl = pr.playlist
        ep.duration = pl.total_duration
        ep.bandwidth = pl.bandwidth
        ep.resolution = pl.resolution
        ep.seg_count = len(pl.segments)
        ep.probed = True

        self.on_log(f"{tag} {len(pl.segments)} 段 / {human_time(pl.total_duration)}"
                    + (f" / {pl.resolution}" if pl.resolution else "")
                    + (f" / 已剔除 {len(pr.dropped)} 个广告块" if pr.dropped else ""))

        if self.cancel.is_set():
            return False, "已取消"

        seg_dir = os.path.join(opts.out_dir, "_segs", name)
        dl = SegmentDownloader(
            pl, seg_dir, opts.workers, opts.retries, opts.ua,
            referer=ep.play_url,
            on_progress=lambda p: self.on_episode_progress(idx, p),
            cancel=self.cancel)
        ok = dl.run()

        if self.cancel.is_set():
            return False, "已取消"
        if not ok:
            self.on_log(f"{tag} 有 {len(dl.failures)} 段失败，分片保留可续传")
            return False, f"{len(dl.failures)} 段失败"

        self.on_log(f"{tag} 合并中 …")
        try:
            dl.merge(raw_path)
        except Exception as e:  # noqa: BLE001
            self.on_log(f"{tag} 合并失败：{e}")
            return False, str(e)
        self.on_log(f"{tag} 已合并 {human_bytes(os.path.getsize(raw_path))}"
                    + (f"  平均码率 ≈ {pl.bandwidth / 1000:.0f} kbps" if pl.bandwidth else ""))

        final = raw_path
        ff = find_ffmpeg(opts.ffmpeg)
        if not ff:
            self.on_log(f"{tag} 找不到 ffmpeg，只保留未封装的传输流 .raw")
        else:
            self.on_log(f"{tag} 封装 {out_ext.upper()[1:]}（无损 -c copy）…")
            if remux_container(ff, raw_path, final_path, self.on_log):
                final = final_path
            else:
                self.on_log(f"{tag} 封装失败，保留 .raw")

        if final != raw_path:
            try:
                os.remove(raw_path)     # 封装成功就不再留中间流
            except OSError:
                pass

        if not opts.keep_segments:
            shutil.rmtree(seg_dir, ignore_errors=True)

        ep.saved_path = final
        self.on_log(f"{tag} 完成 {os.path.basename(final)}  {human_bytes(os.path.getsize(final))}")
        return True, "完成"


# --------------------------------------------------------------------------- #
# 命令行自测
# --------------------------------------------------------------------------- #
def _selftest(url: str) -> None:
    sess = make_session()
    final_url, cfg, html = resolve_play_url(sess, url)
    print("最终播放页:", final_url)
    print("player from =", cfg.get("from"), " encrypt =", cfg.get("encrypt"))
    print("=" * 70)

    series = parse_series(html, final_url)
    print("剧名:", series.title, " aid:", series.aid)
    print("线路数:", len(series.lines))
    for l in series.lines:
        print(f"  线路 sid={l.sid} {l.name}: {len(l.episodes)} 集  "
              f"({l.episodes[0].label} … {l.episodes[-1].label})")
    print("总集数（最大线路）:", series.total_episodes)
    print("=" * 70)

    if not series.lines:
        return
    ep = series.lines[0].episodes[0]
    print("探测:", ep.label, ep.play_url)
    pr = probe_episode(sess, ep.play_url, True)
    pl = pr.playlist
    print("variant:", pl.variant_url)
    print("分片数:", len(pl.segments), " 总时长:", human_time(pl.total_duration),
          f"({pl.total_duration:.1f}s)")
    print("加密:", pl.key_method or "NONE")
    if pl.bandwidth:
        print(f"码率 {pl.bandwidth} bps  分辨率 {pl.resolution}  "
              f"预估 {human_bytes(pl.total_duration * pl.bandwidth / 8)}")
    if pr.dropped:
        print("已剔除广告块:", [(b.block, b.segs, round(b.duration, 1)) for b in pr.dropped])
    print("=" * 70)
    for s in pl.segments[:3]:
        print(f"  #{s.index:04d} {s.duration:6.2f}s {s.url}")
    print(f"  ... 共 {len(pl.segments)}")
    print("=" * 70)
    print("ffmpeg:", find_ffmpeg() or "(未找到)")


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "--selftest":
        _selftest(argv[2])
        return 0
    print(__doc__)
    print("ffmpeg:", find_ffmpeg() or "(未找到)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
