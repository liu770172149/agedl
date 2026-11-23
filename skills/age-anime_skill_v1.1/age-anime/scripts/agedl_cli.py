#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AGE 动漫 — 给 agent 用的 JSON 命令行接口。

所有子命令的 stdout 都是单个 JSON 对象（ensure_ascii=False），
进度与日志一律写 stderr，方便 agent 直接解析结果、不被噪声干扰。

子命令：
    doctor      环境自检（python / ffmpeg / 可写目录）
    hot         站点热门榜单、最新入库、今日更新、新番上架
    search      按关键词搜索站点
    detail      取单个作品的详情（含全部播放页链接）
    series      解析播放页/详情页 → 剧名、线路、集数清单
    probe       探测某集真实 m3u8 地址与分片信息
    download    下载指定集数，输出 MP4 / MKV

示例：
    python agedl_cli.py hot --src 本周排行
    python agedl_cli.py search 命运 --limit 50
    python agedl_cli.py series https://www.age001.com/play/12537-1-1.html
    python agedl_cli.py download https://www.age001.com/play/12537-1-1.html -n 1-3 -f mp4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

# ---------------------------------------------------------------- 编码兜底 --
for _s in (sys.stdout, sys.stderr):
    try:
        if _s is not None and (_s.encoding or "").lower().replace("-", "") != "utf8":
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import core            # noqa: E402
import discover        # noqa: E402
import platform_compat as plat  # noqa: E402

DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "Downloads", "AGE动漫")


# ------------------------------------------------------------------ 输出 --
def emit(obj: dict, code: int = 0) -> int:
    """打印 JSON 并返回退出码。"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
    return code


def elog(msg: str) -> None:
    """进度/日志走 stderr，不污染 JSON。"""
    if sys.stderr is not None:
        sys.stderr.write(str(msg).rstrip() + "\n")
        sys.stderr.flush()


def fail(msg: str, **extra) -> int:
    return emit({"ok": False, "error": str(msg), **extra}, 1)


# ------------------------------------------------------------- 小工具层 --
def resolve_ffmpeg(explicit: str = "") -> str:
    """按优先级找 ffmpeg：

    1. --ffmpeg 显式指定
    2. 环境变量 AGEDL_FFMPEG（换机器最省事的做法）
    3. core.find_ffmpeg()（skill 目录旁边 / 常见安装位置 / PATH）
    """
    if explicit and os.path.isfile(explicit):
        return explicit
    env = os.environ.get("AGEDL_FFMPEG", "").strip().strip('"')
    if env and os.path.isfile(env):
        return env
    return core.find_ffmpeg() or ""


def parse_eps(spec: str, total: int) -> list[int]:
    """'1' / '1-3' / '1,2,5' / 'all' → 集号列表（按集号，不是索引）。"""
    s = (spec or "").strip().lower().replace("，", ",").replace("、", ",")
    if s in ("", "all", "*", "全部"):
        return list(range(1, total + 1))
    out: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                lo = int(a)
                hi = int(b) if b.strip() else total
            except ValueError:
                continue
            if lo > hi:
                lo, hi = hi, lo
            out.update(range(lo, hi + 1))
        else:
            try:
                out.add(int(part))
            except ValueError:
                pass
    return [n for n in sorted(out) if 1 <= n <= total]


def choose_line(series: core.Series, line_spec: str = "",
                ep_spec: str = "1") -> tuple[core.Line, list[int]]:
    """选定线路 + 要处理的集号。

    规则（不指定 --line 时）：
      1. 先按最大的线路集数算出要哪些集号；
      2. 在「包含这批集号的全部线路」里取页面顺序第一条（站点通常把
         主线路/高码率线路排在前面）；
      3. 如果没有一条线路包含全部集号，退回集数最多的那条。
    这样「下载第01集」会走主线路，「下载第13集」会自动切到有第13集的线路。
    """
    lines = series.lines or []
    if not lines:
        raise RuntimeError("该页面没有解析到任何线路")
    total_max = max(len(ln.episodes) for ln in lines)
    want = parse_eps(ep_spec, total_max)
    if not want:
        raise RuntimeError(f"集号 {ep_spec!r} 解析后为空，可用 1 / 1-3 / 1,2,5 / all")
    if line_spec.strip():
        w = line_spec.strip()
        for ln in lines:
            if ln.name == w or str(ln.sid) == w:
                return ln, want
        raise RuntimeError(
            f"没有名为 {w!r} 的线路，可选：{[(l.sid, l.name, len(l.episodes)) for l in lines]}")
    def has_all(ln: core.Line) -> bool:
        have = {ep.nid for ep in ln.episodes}
        return all(n in have for n in want)
    ok = [ln for ln in lines if has_all(ln)]
    if ok:
        return ok[0], want
    return max(lines, key=lambda l: len(l.episodes)), want


def open_series(url: str) -> tuple[core.Series, str]:
    sess = core.make_session()
    final, _cfg, html = core.resolve_play_url(sess, url)
    series = core.parse_series(html, final)
    if not series.lines:
        raise RuntimeError("没解析到线路，可能不是 AGE 的播放页/详情页")
    return series, final


def series_dict(series: core.Series, final: str) -> dict:
    return {
        "title": series.title,
        "aid": series.aid,
        "total_episodes": series.total_episodes,
        "resolved_url": final,
        "lines": [
            {
                "sid": ln.sid,
                "name": ln.name,
                "count": len(ln.episodes),
                "episodes": [
                    {"nid": ep.nid, "label": ep.label, "play_url": ep.play_url}
                    for ep in ln.episodes
                ],
            }
            for ln in series.lines
        ],
    }


def item_dict(it: discover.VodItem) -> dict:
    return {
        "vid": it.vid,
        "name": it.name,
        "year": it.year,
        "area": it.area,
        "lang": it.lang,
        "remarks": it.remarks,
        "tags": it.tags,
        "type_name": it.type_name,
        "heat": it.hits,
        "rank": it.rank,
        "updated": it.updated,
        "blurb": it.blurb,
        "detail_url": it.web_url,
        "play_url": it.play_url,
        "pic": it.pic,
    }


# -------------------------------------------------------------- 子命令 --
def cmd_doctor(args) -> int:
    ff = resolve_ffmpeg(args.ffmpeg)
    out_dir = os.path.abspath(args.out)
    writable = False
    probe_file = ""
    try:
        os.makedirs(out_dir, exist_ok=True)
        probe_file = os.path.join(out_dir, f"._w_{os.getpid()}.tmp")
        with open(probe_file, "wb") as f:
            f.write(b"ok")
        writable = True
    except Exception as exc:  # noqa: BLE001
        elog(f"目录不可写：{exc}")
    finally:
        try:
            if probe_file and os.path.isfile(probe_file):
                os.remove(probe_file)
        except Exception:
            pass
    info = plat.describe()
    if ff:
        try:
            ff_exe_ok = os.access(ff, os.X_OK)
        except OSError:
            ff_exe_ok = False
        hint = ""
        if not ff_exe_ok and not info["is_windows"]:
            hint = "ffmpeg 没有执行权限，运行 chmod +x 后重试"
        elif not os.access(os.path.dirname(ff) or ".", os.W_OK):
            hint = "ffmpeg 所在目录不可写；若封装报 Permission denied，core 会自动把它复制到临时目录再跑"
    else:
        ff_exe_ok = False
        hint = plat.install_hint()

    return emit({
        "ok": True,
        "platform": info,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "ffmpeg": ff or None,
        "ffmpeg_version": core.ffmpeg_version(ff) if ff else None,
        "ffmpeg_executable": ff_exe_ok,
        "out_dir": out_dir,
        "out_writable": writable,
        "hint": hint,
    })


def cmd_hot(args) -> int:
    names = [n for n, _k in discover.SOURCES]
    if args.src and args.src not in names:
        return fail(f"未知数据源 {args.src!r}", sources=names)
    key = ""
    title = ""
    for n, k in discover.SOURCES:
        if not args.src or n == args.src:
            key, title = k, n
            break
    sess = discover.site_session()
    data = discover.load_source(sess, key, page=max(1, args.page))
    items = data.get("items") or []
    return emit({
        "ok": True,
        "source": title,
        "key": key,
        "page": data.get("page", 1),
        "pagecount": data.get("pagecount"),
        "total": data.get("total"),
        "count": len(items),
        "boards": [
            {"group": b.group, "count": b.count,
             "top_value": b.top_value, "avg_value": b.avg_value}
            for b in (data.get("boards") or [])
        ],
        "items": [item_dict(it) for it in items],
        "sources": names,
    })


def cmd_search(args) -> int:
    sess = discover.site_session()
    data = discover.search_vods(sess, args.keyword, limit=max(1, min(args.limit, 200)))
    items = data.get("items") or []
    return emit({
        "ok": True,
        "keyword": args.keyword,
        "total": data.get("total"),
        "count": len(items),
        "items": [item_dict(it) for it in items],
    })


def cmd_detail(args) -> int:
    vid = 0
    target = args.target.strip()
    if target.isdigit():
        vid = int(target)
    else:
        import re
        m = re.search(r"/vod/(\d+)\.html", target) or re.search(r"/play/(\d+)-", target) \
            or re.search(r"/play/(\d+)", target)
        if m:
            vid = int(m.group(1))
    if not vid:
        return fail(f"无法从 {target!r} 里取出作品 id")
    sess = discover.site_session()
    d = discover.fetch_detail(sess, vid=vid)
    it = d["item"]
    return emit({
        "ok": True,
        "item": item_dict(it),
        "kvs": d.get("kvs") or {},
        "play_count": len(d.get("plays") or []),
        "plays": d.get("plays") or [],
    })


def cmd_series(args) -> int:
    series, final = open_series(args.url)
    return emit({"ok": True, **series_dict(series, final)})


def cmd_probe(args) -> int:
    series, final = open_series(args.url)
    line, want = choose_line(series, args.line, args.episodes)
    total = len(line.episodes)
    sess = core.make_session()
    out = []
    for ep in line.episodes:
        if ep.nid not in want:
            continue
        elog(f"探测 第{ep.nid:02d}集 …")
        try:
            pr = core.probe_episode(sess, ep.play_url, drop_ads=not args.keep_ads)
        except Exception as exc:  # noqa: BLE001
            out.append({"nid": ep.nid, "label": ep.label,
                        "error": f"{type(exc).__name__}: {exc}"})
            continue
        pl = pr.playlist
        segs = pl.segments
        out.append({
            "nid": ep.nid,
            "label": ep.label,
            "play_url": ep.play_url,
            "variant_url": pl.variant_url,
            "segments": len(segs),
            "duration": round(pl.total_duration, 1),
            "duration_text": core.human_time(pl.total_duration),
            "bandwidth": pl.bandwidth,
            "resolution": pl.resolution,
            "key_method": pl.key_method,
            "dropped_blocks": [
                {"block": b.block, "segs": b.segs,
                 "duration": round(b.duration, 1), "src": b.src}
                for b in pr.dropped
            ],
            "first_segment": segs[0].url if segs else "",
            "last_segment": segs[-1].url if segs else "",
            "estimate_bytes": int(pl.total_duration * pl.bandwidth / 8) if pl.bandwidth else None,
            "estimate_text": core.human_bytes(pl.total_duration * pl.bandwidth / 8)
            if pl.bandwidth else None,
        })
    return emit({
        "ok": True,
        "title": series.title,
        "aid": series.aid,
        "line": {"sid": line.sid, "name": line.name, "count": total},
        "resolved_url": final,
        "probed": out,
    })


def cmd_download(args) -> int:
    ff = resolve_ffmpeg(args.ffmpeg)
    if not ff:
        elog("⚠ 未找到 ffmpeg：本次只下载并合并出 .raw 中间流，不会封装成 MP4/MKV。")
        elog("  装好 ffmpeg 后可执行：agedl_cli.py convert <目录>  批量转成 .mp4")
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    series, final = open_series(args.url)
    line, want = choose_line(series, args.line, args.episodes)
    picks = [ep for ep in line.episodes if ep.nid in want]

    opts = core.JobOptions(
        out_dir=out_dir,
        fmt=args.fmt,
        workers=max(1, min(args.workers, 64)),
        retries=max(1, args.retries),
        drop_ads=not args.keep_ads,
        keep_segments=args.keep_segments,
        ffmpeg=ff,
    )
    started = time.time()
    done_first = {"t": None}

    def on_log(m: str) -> None:
        elog(f"[{time.strftime('%H:%M:%S')}] {m}")

    def on_overall(i: int, n: int, label: str) -> None:
        if i < n:
            elog(f"== 第 {i + 1}/{n} 集：{label} ==")

    def on_ep_progress(_i: int, p: core.Progress) -> None:
        if p.done and (p.done % 50 == 0 or p.done == p.total):
            elog(f"    {p.done}/{p.total} 段 {p.percent:.1f}% "
                 f"{core.human_bytes(p.nbytes)} {p.speed / 1048576:.1f} MB/s")

    def on_ep_done(ep: core.Episode, ok: bool, msg: str) -> None:
        if ok and done_first["t"] is None:
            done_first["t"] = time.time() - started
        elog(f"    {'✓' if ok else '✗'} {ep.label} {msg}")

    job = core.Job(series, picks, opts, on_log=on_log,
                   on_episode_progress=on_ep_progress,
                   on_overall=on_overall,
                   on_episode_done=on_ep_done)
    ok_count, fail_count = job.run()

    files = []
    for ep in picks:
        p = ep.saved_path or ""
        files.append({
            "nid": ep.nid,
            "label": ep.label,
            "status": ep.status,
            "path": p,
            "bytes": os.path.getsize(p) if p and os.path.isfile(p) else None,
        })
    return emit({
        "ok": fail_count == 0,
        "title": series.title,
        "line": {"sid": line.sid, "name": line.name},
        "fmt": args.fmt,
        "out_dir": out_dir,
        "requested": len(picks),
        "ok_count": ok_count,
        "fail_count": fail_count,
        "elapsed": round(time.time() - started, 1),
        "files": files,
    }, 0 if fail_count == 0 else 2)


def cmd_selftest(args) -> int:
    """跨平台单元测试：两套（纯逻辑 + POSIX 端到端）。

    纯逻辑那套不需要网络也不需要 ffmpeg；POSIX 那套会真的跑一次
    分片合并与封装，需要 ffmpeg，缺了就把该套标成跳过。
    """
    import subprocess

    suites = [
        ("platform", "test_platform.py", "跨平台逻辑"),
        ("posix", "test_posix_sim.py", "POSIX 端到端"),
    ]
    results = []
    all_ok = True

    for key, fname, label in suites:
        path = os.path.join(HERE, fname)
        if not os.path.isfile(path):
            all_ok = False
            results.append({
                "name": key, "label": label, "file": fname,
                "ok": False, "skipped": True, "returncode": None,
                "summary": "测试文件缺失", "report": "", "stderr": "",
            })
            continue
        elog("运行 " + label + " 测试：" + fname + " …")
        try:
            p = subprocess.run(
                [sys.executable, path],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=args.timeout,
                **plat.spawn_kwargs(),
            )
            out = p.stdout or ""
            err = p.stderr or ""
            tail = [ln for ln in out.splitlines()
                    if ln.strip().startswith("结果：")]
            summary = tail[-1].strip() if tail else "无汇总行"
            ok = p.returncode == 0
            all_ok = all_ok and ok
            results.append({
                "name": key, "label": label, "file": fname,
                "ok": ok, "skipped": False, "returncode": p.returncode,
                "summary": summary, "report": out[-4000:], "stderr": err[-1000:],
            })
            elog("  → " + summary)
        except subprocess.TimeoutExpired:
            all_ok = False
            results.append({
                "name": key, "label": label, "file": fname,
                "ok": False, "skipped": False, "returncode": None,
                "summary": "超时（>" + str(args.timeout) + "s）",
                "report": "", "stderr": "",
            })
            elog("  → 超时")

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    head = str(passed) + "/" + str(total) + " 套测试通过"
    elog(head)
    return emit({
        "ok": all_ok,
        "platform": plat.describe(),
        "summary": head,
        "suites": results,
    }, 0 if all_ok else 1)


def cmd_convert(args) -> int:
    """把遗留的 .raw 批量转成 mp4（早期版本可能留下）。"""
    ff = resolve_ffmpeg(args.ffmpeg)
    if not ff:
        return fail("找不到 ffmpeg")
    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        return fail(f"目录不存在：{folder}")
    raws = sorted(f for f in os.listdir(folder) if f.lower().endswith(".raw"))
    if not raws:
        return emit({"ok": True, "folder": folder, "converted": [], "message": "没有 .raw 文件"})
    converted, failed = [], []
    for name in raws:
        src = os.path.join(folder, name)
        dst = os.path.join(folder, os.path.splitext(name)[0] + ".mp4")
        if os.path.isfile(dst) and os.path.getsize(dst) > 0:
            converted.append({"file": dst, "skipped": True})
            continue
        elog(f"转换 {name} …")
        if core.remux_container(ff, src, dst, on_log=lambda m: elog("  " + m)):
            if not args.keep:
                try:
                    os.remove(src)
                except OSError:
                    pass
            converted.append({"file": dst, "bytes": os.path.getsize(dst)})
        else:
            failed.append(name)
    return emit({"ok": not failed, "folder": folder,
                 "converted": converted, "failed": failed},
                0 if not failed else 2)


# ------------------------------------------------------------------ 入口 --
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agedl_cli", add_help=True,
        description="AGE 动漫 agent 接口（输出 JSON）")
    sub = p.add_subparsers(dest="cmd", required=False)

    def add_common(sp, need_out=False):
        sp.add_argument("--ffmpeg", default="",
                        help="ffmpeg 可执行文件路径（也可用环境变量 AGEDL_FFMPEG）")
        if need_out:
            sp.add_argument("-o", "--out", default=DEFAULT_OUT, help="输出目录")
        return sp

    add_common(sub.add_parser("doctor", help="环境自检"), need_out=True)

    sp = sub.add_parser("hot", help="热门/榜单/最新入库")
    sp.add_argument("--src", default="", help="数据源名称，留空用第一个")
    sp.add_argument("--page", type=int, default=1, help="页码（仅最新入库有效）")

    sp = sub.add_parser("search", help="关键词搜索")
    sp.add_argument("keyword")
    sp.add_argument("--limit", type=int, default=100, help="最多 200")

    sp = sub.add_parser("detail", help="作品详情")
    sp.add_argument("target", help="作品 id 或 /vod/N.html 网址")

    sp = sub.add_parser("series", help="解析播放页 → 剧名/线路/集数")
    sp.add_argument("url")

    sp = sub.add_parser("probe", help="探测某集真实 m3u8")
    sp.add_argument("url")
    sp.add_argument("-n", "--episodes", default="1", help="集号，如 1 / 1-3 / 1,2,5")
    sp.add_argument("--line", default="", help="线路名或 sid，留空取集数最多那条")
    sp.add_argument("--keep-ads", action="store_true", help="保留广告分片")

    sp = sub.add_parser("download", help="下载剧集")
    sp.add_argument("url")
    sp.add_argument("-n", "--episodes", default="1", help="集号，如 1 / 1-3 / all")
    sp.add_argument("--line", default="", help="线路名或 sid")
    sp.add_argument("-f", "--fmt", default="mp4", choices=["mp4", "mkv"])
    sp.add_argument("-w", "--workers", type=int, default=24)
    sp.add_argument("-r", "--retries", type=int, default=5)
    sp.add_argument("--keep-ads", action="store_true")
    sp.add_argument("--keep-segments", action="store_true")
    add_common(sp, need_out=True)

    sp = sub.add_parser("selftest", help="跨平台单元测试（纯逻辑 + POSIX 端到端）")
    sp.add_argument("--timeout", type=int, default=600, help="每套测试的超时秒数，默认 600")

    sp = sub.add_parser("convert", help="批量把 .raw 转 mp4")
    sp.add_argument("folder")
    sp.add_argument("--keep", action="store_true", help="保留 .raw")
    add_common(sp)

    return p


HANDLERS = {
    "doctor": cmd_doctor,
    "hot": cmd_hot,
    "search": cmd_search,
    "detail": cmd_detail,
    "series": cmd_series,
    "probe": cmd_probe,
    "download": cmd_download,
    "convert": cmd_convert, "selftest": cmd_selftest,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        parser.print_help(sys.stderr)
        return emit({"ok": False, "error": "缺少子命令",
                     "commands": sorted(HANDLERS)}, 1)
    args = parser.parse_args(argv)
    fn = HANDLERS.get(args.cmd)
    if not fn:
        return fail(f"未知子命令 {args.cmd!r}", commands=sorted(HANDLERS))
    try:
        return fn(args)
    except KeyboardInterrupt:
        return fail("已中断")
    except Exception as exc:  # noqa: BLE001
        import traceback
        elog(traceback.format_exc())
        return fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
