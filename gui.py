#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui.py —— AGE动漫 视频下载器（图形界面）

界面流程：
  1. 粘贴播放页地址（/play/xxx-1-1.html）→ 点「解析」
  2. 程序读出剧名、总集数、各线路集数
  3. 在表格里勾选要下载的集（支持全选 / 反选 / 按范围选）
  4. 选输出格式（MP4 / MKV，均无损封装）
  5. 点「开始下载」，实时显示总进度、单集进度、速度、日志
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import time
import traceback
import webbrowser
from dataclasses import dataclass, field
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core
import discover

APP_NAME = "AGE动漫 视频下载器"
APP_VER = "1.2"

CHECK_ON = "☑"
CHECK_OFF = "☐"


# --------------------------------------------------------------------------- #
# 后台 → 界面 消息
# --------------------------------------------------------------------------- #
@dataclass
class Msg:
    kind: str                      # log / series / rows / ep_progress / overall / ep_done / done / error / probe_row
    payload: object = None


class Bridge:
    """把工作线程的事件安全地送回 Tk 主线程。"""

    def __init__(self, q: queue.Queue):
        self.q = q

    def log(self, text: str) -> None:
        self.q.put(Msg("log", text))

    def series(self, s) -> None:
        self.q.put(Msg("series", s))

    def rows(self) -> None:
        self.q.put(Msg("rows", None))

    def probe_row(self, idx: int) -> None:
        self.q.put(Msg("probe_row", idx))

    def ep_progress(self, idx: int, p) -> None:
        self.q.put(Msg("ep_progress", (idx, p)))

    def overall(self, done: int, total: int, label: str) -> None:
        self.q.put(Msg("overall", (done, total, label)))

    def ep_done(self, idx: int, ok: bool, msg: str) -> None:
        self.q.put(Msg("ep_done", (idx, ok, msg)))

    def done(self, ok: int, fail: int) -> None:
        self.q.put(Msg("done", (ok, fail)))

    def error(self, text: str) -> None:
        self.q.put(Msg("error", text))


# --------------------------------------------------------------------------- #
# 主窗口
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VER}")
        self.geometry("1120x760")
        self.minsize(980, 640)

        self.q: queue.Queue = queue.Queue()
        self.bridge = Bridge(self.q)

        self.series: Optional[core.Series] = None
        self.line: Optional[core.Line] = None
        self.checked: dict[int, bool] = {}       # ep.nid -> 是否勾选
        self.row_iid: dict[int, str] = {}        # ep.nid -> tree iid

        self.cancel = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.prober: Optional[threading.Thread] = None
        self.busy = False

        # 发现页状态
        self.d_items: list = []
        self._d_busy = False
        self._d_pending = None
        self._d_page = 1
        self._d_detail_cache: dict = {}

        self.out_dir = tk.StringVar(value=os.path.join(
            os.path.expanduser("~"), "Downloads", "AGE动漫"))
        self.url_var = tk.StringVar()
        self.fmt_var = tk.StringVar(value="mp4")
        self.workers_var = tk.IntVar(value=16)
        self.drop_ads_var = tk.BooleanVar(value=True)
        self.keep_seg_var = tk.BooleanVar(value=False)
        self.ffmpeg_var = tk.StringVar(value=core.find_ffmpeg() or "")
        self.status_var = tk.StringVar(value="就绪")
        self.info_var = tk.StringVar(value="粘贴播放页地址后点「解析」")
        self.line_var = tk.StringVar()
        self.overall_var = tk.StringVar(value="总进度  0 / 0")
        self.ep_var = tk.StringVar(value="当前集  -")

        self._build_ui()
        self.after(80, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._check_ffmpeg()

    # ------------------------------------------------------------------ UI #
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=24)
        style.configure("Big.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 10, "bold"),
                        padding=(18, 6))

        # ---- 两个 tab ----
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)

        page_dl = ttk.Frame(self.nb)
        self.nb.add(page_dl, text="  下载  ")
        page_disc = ttk.Frame(self.nb)
        self.nb.add(page_disc, text="  发现 / 热门  ")

        self._build_download_ui(page_dl)
        self._build_discover_ui(page_disc)

        # 第一次切到「发现」页时自动加载本周排行
        self._d_loaded_once = False
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, _ev=None) -> None:
        try:
            if self.nb.index(self.nb.select()) != 1:
                return
        except tk.TclError:
            return
        if self._d_loaded_once:
            return
        # 用户已经在加载/搜索了，别再插一个默认榜单把结果冲掉
        if getattr(self, "_d_busy", False) or getattr(self, "d_items", None):
            self._d_loaded_once = True
            return
        self._d_loaded_once = True
        self.on_discover_load()

    # ---------------------------------------------------- tab 1：下载界面 #
    def _build_download_ui(self, root: tk.Misc) -> None:
        # ---- 地址栏 ----
        top = ttk.LabelFrame(root, text=" 1. 粘贴网站地址 ")
        top.pack(fill="x", padx=10, pady=(10, 6))
        inner = ttk.Frame(top)
        inner.pack(fill="x", padx=10, pady=8)

        ttk.Label(inner, text="播放页 URL：").pack(side="left")
        self.url_entry = ttk.Entry(inner, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.url_entry.bind("<Return>", lambda _e: self.on_parse())
        self.btn_paste = ttk.Button(inner, text="从剪贴板", width=11, command=self.on_paste)
        self.btn_paste.pack(side="left", padx=(0, 6))
        self.btn_open = ttk.Button(inner, text="打开网页", width=10,
                                   command=lambda: webbrowser.open(self.url_var.get().strip())
                                   if self.url_var.get().strip() else None)
        self.btn_open.pack(side="left", padx=(0, 6))
        self.btn_parse = ttk.Button(inner, text="解析", width=10,
                                    style="Big.TButton", command=self.on_parse)
        self.btn_parse.pack(side="left")

        row2 = ttk.Frame(top)
        row2.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(row2, textvariable=self.info_var, foreground="#1a4f8b",
                  font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")

        # ---- 集数选择 ----
        mid = ttk.LabelFrame(root, text=" 2. 选择要下载的集 ")
        mid.pack(fill="both", expand=False, padx=10, pady=6)

        linebar = ttk.Frame(mid)
        linebar.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(linebar, text="线路：").pack(side="left")
        self.line_combo = ttk.Combobox(linebar, textvariable=self.line_var,
                                       state="readonly", width=28)
        self.line_combo.pack(side="left", padx=(0, 12))
        self.line_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_line_change())

        ttk.Button(linebar, text="探测全部集详情", width=16,
                   command=self.on_probe_all).pack(side="left", padx=(0, 6))
        self.count_var = tk.StringVar(value="已选 0 集")
        ttk.Label(linebar, textvariable=self.count_var,
                  font=("Microsoft YaHei UI", 9, "bold")).pack(side="right")

        selbar = ttk.Frame(mid)
        selbar.pack(fill="x", padx=10, pady=(0, 6))
        for txt, fn in (("全选", self.sel_all), ("全不选", self.sel_none), ("反选", self.sel_invert)):
            ttk.Button(selbar, text=txt, width=7, command=fn).pack(side="left", padx=(0, 5))
        ttk.Label(selbar, text="   按范围：第").pack(side="left")
        self.range_a = tk.StringVar(value="1")
        self.range_b = tk.StringVar(value="3")
        ttk.Spinbox(selbar, from_=1, to=9999, width=5, textvariable=self.range_a).pack(side="left")
        ttk.Label(selbar, text="集 到 第").pack(side="left")
        ttk.Spinbox(selbar, from_=1, to=9999, width=5, textvariable=self.range_b).pack(side="left")
        ttk.Label(selbar, text="集").pack(side="left")
        ttk.Button(selbar, text="选择此范围", width=11,
                   command=self.sel_range).pack(side="left", padx=(6, 0))

        # 表格
        tbl = ttk.Frame(mid)
        tbl.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        cols = ("sel", "nid", "label", "dur", "res", "rate", "size", "status")
        self.tree = ttk.Treeview(tbl, columns=cols, show="headings", height=9,
                                 selectmode="extended")
        heads = {
            "sel": ("选", 44), "nid": ("#", 44), "label": ("集数", 130),
            "dur": ("时长", 82), "res": ("分辨率", 92), "rate": ("码率", 92),
            "size": ("预估大小", 100), "status": ("状态 / 备注", 300),
        }
        for c in cols:
            text, w = heads[c]
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor="center" if c != "status" else "w",
                             stretch=(c == "status"))
        vs = ttk.Scrollbar(tbl, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<space>", self.on_tree_space)

        # ---- 输出选项 ----
        bot = ttk.LabelFrame(root, text=" 3. 输出设置 ")
        bot.pack(fill="x", padx=10, pady=6)
        r = ttk.Frame(bot)
        r.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(r, text="保存到：").pack(side="left")
        ttk.Entry(r, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(r, text="浏览…", width=9, command=self.on_browse_out).pack(side="left")
        ttk.Button(r, text="打开目录", width=10,
                   command=self.on_open_out).pack(side="left", padx=(6, 0))

        r2 = ttk.Frame(bot)
        r2.pack(fill="x", padx=10, pady=(4, 8))
        ttk.Label(r2, text="格式：").pack(side="left")
        ttk.Radiobutton(r2, text="MP4（无损封装，推荐）", value="mp4",
                        variable=self.fmt_var).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(r2, text="MKV（原始流无损封装）", value="mkv",
                        variable=self.fmt_var).pack(side="left", padx=(0, 20))

        ttk.Label(r2, text="并发：").pack(side="left")
        ttk.Spinbox(r2, from_=1, to=64, width=5, textvariable=self.workers_var).pack(side="left")
        ttk.Label(r2, text="   ").pack(side="left")
        ttk.Checkbutton(r2, text="自动剔除广告段", variable=self.drop_ads_var).pack(side="left")
        ttk.Checkbutton(r2, text="保留分片缓存", variable=self.keep_seg_var).pack(side="left", padx=(10, 0))

        r3 = ttk.Frame(bot)
        r3.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(r3, text="ffmpeg：").pack(side="left")
        ttk.Entry(r3, textvariable=self.ffmpeg_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(r3, text="浏览…", width=9, command=self.on_browse_ffmpeg).pack(side="left")
        self.ff_state = tk.StringVar(value="检测中…")
        ttk.Label(r3, textvariable=self.ff_state, width=26).pack(side="left", padx=(8, 0))

        # ---- 进度 + 操作 ----
        pr = ttk.LabelFrame(root, text=" 4. 下载 ")
        pr.pack(fill="x", padx=10, pady=6)
        p1 = ttk.Frame(pr)
        p1.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(p1, textvariable=self.overall_var, width=32).pack(side="left")
        self.pb_all = ttk.Progressbar(p1, mode="determinate", maximum=100)
        self.pb_all.pack(side="left", fill="x", expand=True, padx=8)
        p2 = ttk.Frame(pr)
        p2.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(p2, textvariable=self.ep_var, width=32).pack(side="left")
        self.pb_ep = ttk.Progressbar(p2, mode="determinate", maximum=100)
        self.pb_ep.pack(side="left", fill="x", expand=True, padx=8)

        act = ttk.Frame(pr)
        act.pack(fill="x", padx=10, pady=(0, 8))
        self.btn_start = ttk.Button(act, text="开始下载", width=16, style="Big.TButton",
                                    command=self.on_start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(act, text="停止", width=10, state="disabled",
                                   command=self.on_stop)
        self.btn_stop.pack(side="left", padx=(8, 0))
        ttk.Label(act, textvariable=self.status_var, foreground="#555").pack(side="left", padx=(16, 0))

        # ---- 日志 ----
        lg = ttk.LabelFrame(root, text=" 运行日志 ")
        lg.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_txt = tk.Text(lg, height=8, wrap="none", font=("Consolas", 9),
                               bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4")
        lv = ttk.Scrollbar(lg, orient="vertical", command=self.log_txt.yview)
        self.log_txt.configure(yscrollcommand=lv.set, state="disabled")
        self.log_txt.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=8)
        lv.pack(side="right", fill="y", pady=8, padx=(0, 10))

    # ------------------------------------------------ tab 2：发现 / 热门 #
    def _build_discover_ui(self, root: tk.Misc) -> None:
        # ---- 搜索 / 数据源 ----
        bar = ttk.LabelFrame(root, text=" 搜索与数据源 ")
        bar.pack(fill="x", padx=8, pady=(8, 6))
        r1 = ttk.Frame(bar)
        r1.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(r1, text="搜片名：").pack(side="left")
        self.d_search_var = tk.StringVar()
        e = ttk.Entry(r1, textvariable=self.d_search_var)
        e.pack(side="left", fill="x", expand=True, padx=(0, 8))
        e.bind("<Return>", lambda _ev: self.on_discover_search())
        self.btn_d_search = ttk.Button(r1, text="搜索", width=10, style="Big.TButton",
                                       command=self.on_discover_search)
        self.btn_d_search.pack(side="left", padx=(0, 6))
        ttk.Button(r1, text="清空", width=7,
                   command=self.on_discover_clear).pack(side="left")

        r2 = ttk.Frame(bar)
        r2.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(r2, text="热门榜：").pack(side="left")
        self.d_src_var = tk.StringVar(value=discover.SOURCES[0][0])
        self.d_src_combo = ttk.Combobox(
            r2, textvariable=self.d_src_var, state="readonly", width=14,
            values=[n for n, _k in discover.SOURCES])
        self.d_src_combo.pack(side="left", padx=(0, 8))
        self.d_src_combo.bind("<<ComboboxSelected>>", lambda _ev: self.on_discover_load())
        self.btn_d_load = ttk.Button(r2, text="加载", width=8,
                                     command=self.on_discover_load)
        self.btn_d_load.pack(side="left", padx=(0, 14))

        ttk.Label(r2, text="第").pack(side="left")
        self.d_page_var = tk.StringVar(value="1")
        self.d_page_spin = ttk.Spinbox(r2, from_=1, to=9999, width=5,
                                       textvariable=self.d_page_var)
        self.d_page_spin.pack(side="left")
        ttk.Label(r2, text="页").pack(side="left", padx=(0, 6))
        self.btn_d_page = ttk.Button(r2, text="翻页", width=8,
                                     command=self.on_discover_page)
        self.btn_d_page.pack(side="left", padx=(0, 14))
        self.btn_d_more = ttk.Button(r2, text="下一页 ▸", width=10,
                                     command=self.on_discover_next)
        self.btn_d_more.pack(side="left")
        self.d_stat_var = tk.StringVar(value="选一个数据源，点「加载」")
        ttk.Label(r2, textvariable=self.d_stat_var, foreground="#1a4f8b",
                  font=("Microsoft YaHei UI", 9, "bold")).pack(side="right")

        # ---- 结果表 ----
        mid = ttk.Frame(root)
        mid.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        left = ttk.Frame(mid)
        left.pack(side="left", fill="both", expand=True)
        cols = ("rank", "name", "year", "area", "rem", "heat", "tags")
        self.d_tree = ttk.Treeview(left, columns=cols, show="headings", height=14,
                                   selectmode="browse")
        heads = {
            "rank": ("#", 46), "name": ("片名", 300), "year": ("年份", 60),
            "area": ("地区", 78), "rem": ("状态", 120), "heat": ("热度", 74),
            "tags": ("标签", 230),
        }
        for c in cols:
            text, w = heads[c]
            self.d_tree.heading(c, text=text)
            self.d_tree.column(c, width=w,
                               anchor="w" if c in ("name", "tags") else "center",
                               stretch=(c in ("name", "tags")))
        dvs = ttk.Scrollbar(left, orient="vertical", command=self.d_tree.yview)
        self.d_tree.configure(yscrollcommand=dvs.set)
        self.d_tree.pack(side="left", fill="both", expand=True)
        dvs.pack(side="right", fill="y")
        self.d_tree.bind("<<TreeviewSelect>>", lambda _ev: self.on_discover_select())
        self.d_tree.bind("<Double-1>", lambda _ev: self.on_discover_open_web())

        # ---- 详情面板 ----
        right = ttk.LabelFrame(mid, text=" 详情 ")
        right.pack(side="right", fill="y", padx=(8, 0))
        self.d_detail = tk.Text(right, width=40, height=14, wrap="word",
                                font=("Microsoft YaHei UI", 9),
                                bg="#fbfbfb", fg="#222", state="disabled",
                                relief="flat")
        self.d_detail.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        act = ttk.Frame(right)
        act.pack(fill="x", padx=8, pady=(0, 8))
        self.btn_d_dl = ttk.Button(act, text="去下载此片", width=13,
                                   style="Big.TButton", state="disabled",
                                   command=self.on_discover_to_download)
        self.btn_d_dl.pack(fill="x", pady=(0, 4))
        ttk.Button(act, text="在浏览器打开", width=13,
                   command=self.on_discover_open_web).pack(fill="x", pady=(0, 4))
        ttk.Button(act, text="复制播放页地址", width=13,
                   command=self.on_discover_copy_play).pack(fill="x")

        # ---- 说明 ----
        tip = ttk.Label(
            root,
            text="数据源：本周/本月/总排行榜 · 最新入库（28528 部，可翻页）· 今日更新 · 新番上架 · 首页更新。"
                 "搜索走站点 ajax 接口，中文可用。",
            foreground="#777", font=("Microsoft YaHei UI", 8))
        tip.pack(fill="x", padx=12, pady=(0, 8))

    # ----------------------------------------------------- 发现页事件 #
    def _d_stat(self, text: str) -> None:
        self.d_stat_var.set(text)

    def _d_set_detail(self, text: str) -> None:
        self.d_detail.configure(state="normal")
        self.d_detail.delete("1.0", "end")
        self.d_detail.insert("1.0", text)
        self.d_detail.configure(state="disabled")

    def d_log(self, text: str) -> None:
        """发现页的日志也写到下载页的日志框，保持只有一处日志。"""
        self.log(f"[发现] {text}")

    def _d_buttons(self, state: str) -> None:
        for b in (self.btn_d_search, self.btn_d_load, self.btn_d_page, self.btn_d_more):
            try:
                b.configure(state=state)
            except tk.TclError:
                pass

    def _d_worker(self, fn, done_text: str = "") -> None:
        """在后台线程跑一个发现页任务（避免卡死界面）。

        若上一个任务还在跑，不直接丢弃，而是记成"待办"（后来的覆盖先来的），
        等 d_idle 时再接着跑，这样切 tab 的自动加载不会挡住用户马上点搜索。
        """
        if getattr(self, "_d_busy", False):
            self._d_pending = (fn, done_text)
            self._d_stat("正在加载，稍后自动切换到你的请求 …")
            return
        self._d_pending = None
        self._d_busy = True
        self._d_buttons("disabled")

        def run():
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                self.q.put(Msg("d_error", f"{exc}\n{tb[-600:]}"))
            finally:
                self.q.put(Msg("d_idle", done_text))

        threading.Thread(target=run, daemon=True).start()

    def _d_fill(self, items, source_title: str, total: int = 0,
                page: int = 1, pagecount: int = 1) -> None:
        for iid in self.d_tree.get_children():
            self.d_tree.delete(iid)
        self.d_items = list(items)
        for i, it in enumerate(self.d_items):
            self.d_tree.insert("", "end", iid=str(i), values=self._d_row(it, i))
        pctxt = f"  第 {page} / {pagecount} 页" if pagecount > 1 else ""
        total_txt = f"共 {total} 部" if total else f"{len(self.d_items)} 条"
        self._d_stat(f"{source_title} · {total_txt}{pctxt}")
        if self.d_items:
            self.d_tree.selection_set("0")
            self.d_tree.focus("0")
            self.on_discover_select()
        else:
            self._d_set_detail("（没有结果）")

    def _d_row(self, it, idx: int) -> tuple:
        heat = it.hits or it.hits_week or 0
        heat_txt = f"{heat:,}" if heat else ""
        rank = it.rank or (idx + 1)
        return (rank, it.name, it.year or "-", it.area or "-",
                it.remarks or "-", heat_txt, it.tags or "")

    def on_discover_load(self) -> None:
        name = self.d_src_var.get()
        key = dict(discover.SOURCES).get(name, "rank:本周")
        self._load_source_async(key, name, 1)

    def on_discover_page(self) -> None:
        name = self.d_src_var.get()
        key = dict(discover.SOURCES).get(name, "rank:本周")
        try:
            page = max(1, int(self.d_page_var.get()))
        except Exception:
            page = 1
        self._load_source_async(key, name, page)

    def on_discover_next(self) -> None:
        cur = getattr(self, "_d_page", 1)
        self._d_page = cur + 1
        self.d_page_var.set(str(self._d_page))
        self.on_discover_page()

    def _load_source_async(self, key: str, title: str, page: int) -> None:
        self._d_page = page

        def work():
            sess = discover.site_session()
            d = discover.load_source(sess, key, page)
            self.q.put(Msg("d_rows", (d, title)))

        self._d_worker(work, "")

    def on_discover_search(self) -> None:
        wd = self.d_search_var.get().strip()
        if not wd:
            self._d_stat("先输入要搜的片名")
            return

        def work():
            sess = discover.site_session()
            r = discover.search_vods(sess, wd, limit=200)
            d = {"kind": "list", "title": f"搜索「{wd}」", "boards": [],
                 "items": r["items"], "total": r["total"], "page": 1,
                 "pagecount": 1}
            self.q.put(Msg("d_rows", (d, f"搜索「{wd}」")))

        self._d_worker(work, "")

    def on_discover_clear(self) -> None:
        self.d_search_var.set("")
        self.d_page_var.set("1")
        self._d_page = 1
        self.d_src_var.set(discover.SOURCES[0][0])
        self.on_discover_load()

    def on_discover_select(self) -> None:
        sel = self.d_tree.selection()
        if not sel:
            self.btn_d_dl.configure(state="disabled")
            return
        idx = int(sel[0])
        if idx >= len(getattr(self, "d_items", [])):
            return
        it = self.d_items[idx]
        self.btn_d_dl.configure(state="normal")

        lines = [f"《{it.name}》", ""]
        if it.year:
            lines.append(f"年份：{it.year}")
        if it.area:
            lines.append(f"地区：{it.area}")
        if it.lang:
            lines.append(f"语言：{it.lang}")
        if it.type_name:
            lines.append(f"分类：{it.type_name}")
        if it.remarks:
            lines.append(f"状态：{it.remarks}")
        if it.tags:
            lines.append(f"标签：{it.tags}")
        if it.hits or it.hits_day or it.hits_week:
            lines.append(f"播放：{it.hits}  日 {it.hits_day}  周 {it.hits_week}  月 {it.hits_month}")
        if it.updated:
            lines.append(f"更新：{it.updated}")
        if it.blurb:
            lines.append("")
            lines.append(f"简介：{it.blurb[:400]}")
        lines += ["", f"详情页：{it.web_url}", f"播放页：{it.play_url}"]
        lines.append("")
        lines.append("（双击条目可在浏览器打开详情页）")
        self._d_set_detail("\n".join(lines))

        # suggest / 榜单接口只给 id/name/热度，缺的字段异步补一次详情
        if not (it.year and it.area) and it.vid:
            self._d_fetch_detail(it.vid)

    def _d_fetch_detail(self, vid: int) -> None:
        cache = self._d_detail_cache
        if vid in cache:
            return
        cache[vid] = True          # 占位，避免重复请求

        def work():
            try:
                sess = discover.site_session()
                d = discover.fetch_detail(sess, vid=vid)
                self.q.put(Msg("d_detail", d))
            except Exception:      # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    def _d_apply_detail(self, d: dict) -> None:
        it_new = d.get("item")
        if not it_new:
            return
        for i, it in enumerate(getattr(self, "d_items", [])):
            if it.vid == it_new.vid:
                # 就地补全，保留原有 name/pic
                if it_new.name and not it.name:
                    it.name = it_new.name
                it.year = it_new.year or it.year
                it.area = it_new.area or it.area
                it.lang = it_new.lang or it.lang
                it.remarks = it_new.remarks or it.remarks
                it.tags = it_new.tags or it.tags
                it.type_name = it_new.type_name or it.type_name
                it.updated = it_new.updated or it.updated
                try:
                    self.d_tree.item(str(i), values=self._d_row(it, i))
                except tk.TclError:
                    pass
                sel = self.d_tree.selection()
                if sel and sel[0] == str(i):
                    self._d_render_detail(it, d.get("kvs") or {},
                                          d.get("plays") or [])
                break

    def _d_render_detail(self, it, kvs: dict, plays: list) -> None:
        lines = [f"《{it.name}》", ""]
        for k, v in (kvs or {}).items():
            if v:
                lines.append(f"{k} {v[:160]}")
        if plays:
            lines += ["", f"播放页（{len(plays)} 个）：", plays[0]]
            if len(plays) > 1:
                lines.append(f"  …共 {len(plays)} 集")
        if it.blurb:
            lines.append("")
            lines.append(it.blurb[:400])
        lines += ["", f"详情页：{it.web_url}"]
        lines.append("（双击条目可在浏览器打开详情页）")
        self._d_set_detail("\n".join(lines))

    def _d_current(self):
        sel = self.d_tree.selection()
        if not sel:
            return None
        idx = int(sel[0])
        items = getattr(self, "d_items", [])
        return items[idx] if 0 <= idx < len(items) else None

    def on_discover_open_web(self) -> None:
        it = self._d_current()
        if it and it.web_url:
            webbrowser.open(it.web_url)

    def on_discover_copy_play(self) -> None:
        it = self._d_current()
        if not it:
            return
        url = it.play_url
        self.clipboard_clear()
        self.clipboard_append(url)
        self._d_stat(f"已复制：{url}")

    def on_discover_to_download(self) -> None:
        """把选中作品的播放页地址填到下载页，并自动解析。"""
        it = self._d_current()
        if not it:
            return
        url = it.play_url
        self.url_var.set(url)
        self.nb.select(0)
        self.log(f"[发现] 转到下载：{it.name}  {url}")
        self.on_parse()

    # ------------------------------------------------------------- 辅助 #
    def log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_txt.configure(state="normal")
        self.log_txt.insert("end", f"[{stamp}] {text}\n")
        self.log_txt.see("end")
        self.log_txt.configure(state="disabled")

    def _check_ffmpeg(self) -> None:
        # 注意：tkinter 变量只能在主线程读，所以先在这里取值再交给线程
        hint = self.ffmpeg_var.get().strip()

        def work():
            exe = core.find_ffmpeg(hint)
            if exe:
                ver = core.ffmpeg_version(exe)
                short = ver.replace("ffmpeg version ", "").split(" Copyright")[0].strip()
                self.q.put(Msg("probe_row", ("ff", f"✓ {short[:40]}")))
                if not hint:
                    self.q.put(Msg("ff_path", exe))
            else:
                self.q.put(Msg("probe_row", ("ff", "✗ 未找到（无法封装）")))

        threading.Thread(target=work, daemon=True).start()
        threading.Thread(target=work, daemon=True).start()

    def selected_episodes(self) -> list[core.Episode]:
        if not self.line:
            return []
        return [e for e in self.line.episodes if self.checked.get(e.nid)]

    def _refresh_count(self) -> None:
        n = len(self.selected_episodes())
        tot = len(self.line.episodes) if self.line else 0
        self.count_var.set(f"已选 {n} / {tot} 集")

    # ------------------------------------------------------------- 解析 #
    def on_paste(self) -> None:
        try:
            txt = self.clipboard_get().strip()
        except tk.TclError:
            txt = ""
        if txt:
            self.url_var.set(txt)
            if "/play/" in txt or ".m3u8" in txt.lower():
                self.on_parse()

    def on_parse(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo(APP_NAME, "请先粘贴一个播放页地址。\n例如：\nhttps://age001.com/play/12537-1-1.html")
            return
        if not url.lower().startswith("http"):
            url = "https://" + url
            self.url_var.set(url)

        self.series = None
        self.line = None
        self.checked.clear()
        self.tree.delete(*self.tree.get_children())
        self.row_iid.clear()
        self.info_var.set("正在解析页面 …")
        self.status_var.set("解析中")
        self.btn_parse.configure(state="disabled")
        self.line_combo.configure(values=[])
        self.line_var.set("")

        def work():
            try:
                sess = core.make_session()
                final_url, cfg, html = core.resolve_play_url(sess, url)
                s = core.parse_series(html, final_url)
                self.bridge.series(s)
                self.bridge.log(f"解析成功：{s.title}（aid={s.aid}，{s.total_episodes} 集，"
                                f"{len(s.lines)} 条线路）")
            except Exception as e:  # noqa: BLE001
                self.bridge.error(f"解析失败：{e}")
                self.bridge.log(traceback.format_exc(limit=2).strip())
        threading.Thread(target=work, daemon=True).start()

    def _apply_series(self, s: core.Series) -> None:
        self.series = s
        self.btn_parse.configure(state="normal")
        self.status_var.set("就绪")

        names = [f"{l.name}（{len(l.episodes)} 集）" for l in s.lines]
        self.line_combo.configure(values=names)
        if names:
            self.line_combo.current(0)
            self.on_line_change()

        self.info_var.set(
            f"《{s.title}》   总集数：{s.total_episodes}   线路：{len(s.lines)}   aid={s.aid}")
        self.title(f"{APP_NAME}  v{APP_VER} —— {s.title}")

        # 自动探测第 1 集，让用户看到真实大小
        if self.line and self.line.episodes:
            self._probe_one_async(0)

    def on_line_change(self) -> None:
        if not self.series:
            return
        idx = self.line_combo.current()
        if idx < 0 or idx >= len(self.series.lines):
            return
        self.line = self.series.lines[idx]
        for e in self.line.episodes:
            self.checked[e.nid] = True           # 默认全选
        self._fill_tree()
        self._refresh_count()
        if self.line.episodes:
            self.range_a.set("1")
            self.range_b.set(str(len(self.line.episodes)))
        self.log(f"切换线路：{self.line.name}，共 {len(self.line.episodes)} 集")

    def _fill_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.row_iid.clear()
        if not self.line:
            return
        for i, e in enumerate(self.line.episodes):
            iid = self.tree.insert("", "end", values=self._row_values(e))
            self.row_iid[e.nid] = iid

    def _row_values(self, e: core.Episode) -> tuple:
        est = e.estimate_bytes
        return (
            CHECK_ON if self.checked.get(e.nid) else CHECK_OFF,
            f"{e.nid:02d}",
            e.label,
            core.human_time(e.duration),
            e.resolution or "-",
            f"{e.bandwidth / 1000:.0f} k" if e.bandwidth else "-",
            ("约 " + core.human_bytes(est)) if est else "-",
            e.status if not e.probe_error else f"探测失败：{e.probe_error[:60]}",
        )

    def _refresh_row(self, e: core.Episode) -> None:
        iid = self.row_iid.get(e.nid)
        if iid and self.tree.exists(iid):
            self.tree.item(iid, values=self._row_values(e))

    # --------------------------------------------------------- 勾选操作 #
    def on_tree_click(self, event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        nid = None
        for k, v in self.row_iid.items():
            if v == iid:
                nid = k
                break
        if nid is None or not self.line:
            return
        self.checked[nid] = not self.checked.get(nid)
        for e in self.line.episodes:
            if e.nid == nid:
                self._refresh_row(e)
                break
        self._refresh_count()

    def on_tree_space(self, _e) -> None:
        if not self.line:
            return
        sels = self.tree.selection()
        if not sels:
            return
        rev = {}
        for iid in sels:
            for k, v in self.row_iid.items():
                if v == iid:
                    rev[k] = True
        new = not all(self.checked.get(k) for k in rev) if rev else True
        for k in rev:
            self.checked[k] = new
        for e in self.line.episodes:
            if e.nid in rev:
                self._refresh_row(e)
        self._refresh_count()

    def sel_all(self) -> None:
        if not self.line:
            return
        for e in self.line.episodes:
            self.checked[e.nid] = True
        self._fill_tree()
        self._refresh_count()

    def sel_none(self) -> None:
        if not self.line:
            return
        for e in self.line.episodes:
            self.checked[e.nid] = False
        self._fill_tree()
        self._refresh_count()

    def sel_invert(self) -> None:
        if not self.line:
            return
        for e in self.line.episodes:
            self.checked[e.nid] = not self.checked.get(e.nid, True)
        self._fill_tree()
        self._refresh_count()

    def sel_range(self) -> None:
        if not self.line:
            return
        try:
            a = int(self.range_a.get())
            b = int(self.range_b.get())
        except ValueError:
            messagebox.showwarning(APP_NAME, "范围请填数字")
            return
        if a > b:
            a, b = b, a
        hit = 0
        for e in self.line.episodes:
            on = a <= e.nid <= b
            self.checked[e.nid] = on
            if on:
                hit += 1
        self._fill_tree()
        self._refresh_count()
        self.log(f"按范围选择：第 {a}–{b} 集，共勾选 {hit} 集")

    # ----------------------------------------------------------- 探测 #
    def _probe_one_async(self, index: int) -> None:
        if not self.line or index >= len(self.line.episodes):
            return
        ep = self.line.episodes[index]
        sess = core.make_session()
        # tkinter 变量只能在主线程读，先取值
        drop_ads = bool(self.drop_ads_var.get())

        def work():
            try:
                pr = core.probe_episode(sess, ep.play_url, drop_ads)
                ep.duration = pr.playlist.total_duration
                ep.bandwidth = pr.playlist.bandwidth
                ep.resolution = pr.playlist.resolution
                ep.seg_count = len(pr.playlist.segments)
                ep.key_method = pr.playlist.key_method
                ep.ad_blocks = len(pr.dropped)
                ep.probed = True
                ep.probe_error = None
            except Exception as e:  # noqa: BLE001
                ep.probe_error = str(e)[:120]
            self.bridge.probe_row(ep.nid)
        threading.Thread(target=work, daemon=True).start()

    def on_probe_all(self) -> None:
        if not self.line:
            messagebox.showinfo(APP_NAME, "请先解析一个播放页。")
            return
        if self.prober and self.prober.is_alive():
            return
        if not messagebox.askyesno(
                APP_NAME,
                f"将依次读取 {len(self.line.episodes)} 集的片源信息（分片数、时长、码率）。\n"
                f"每集约需 1–3 秒，不下载视频本体。\n\n继续吗？"):
            return

        self.prober = threading.Thread(target=self._probe_all_worker, daemon=True,
                                       args=(bool(self.drop_ads_var.get()),))
        self.prober.start()

    def _probe_all_worker(self, drop_ads: bool = True) -> None:
        sess = core.make_session()
        eps = list(self.line.episodes)
        self.bridge.log(f"开始探测 {len(eps)} 集片源信息 …")
        for ep in eps:
            if self.cancel.is_set():
                break
            try:
                pr = core.probe_episode(sess, ep.play_url, drop_ads)
                ep.duration = pr.playlist.total_duration
                ep.bandwidth = pr.playlist.bandwidth
                ep.resolution = pr.playlist.resolution
                ep.seg_count = len(pr.playlist.segments)
                ep.key_method = pr.playlist.key_method
                ep.ad_blocks = len(pr.dropped)
                ep.probed = True
                ep.probe_error = None
                self.bridge.log(f"  {ep.label}: {len(pr.playlist.segments)} 段 / "
                                f"{core.human_time(ep.duration)} / "
                                f"{core.human_bytes(ep.estimate_bytes or 0)}")
            except Exception as e:  # noqa: BLE001
                ep.probe_error = str(e)[:120]
                self.bridge.log(f"  {ep.label}: 探测失败 {ep.probe_error}")
            self.bridge.probe_row(ep.nid)
        self.bridge.log("探测结束")

    # ----------------------------------------------------------- 下载 #
    def on_browse_out(self) -> None:
        d = filedialog.askdirectory(initialdir=self.out_dir.get() or os.path.expanduser("~"))
        if d:
            self.out_dir.set(d)

    def on_open_out(self) -> None:
        d = self.out_dir.get().strip()
        if d and os.path.isdir(d):
            os.startfile(d)                                # noqa: S606
        else:
            messagebox.showinfo(APP_NAME, "目录还不存在，下载时会自动创建。")

    def on_browse_ffmpeg(self) -> None:
        p = filedialog.askopenfilename(
            title="选择 ffmpeg.exe",
            filetypes=[("ffmpeg", "ffmpeg.exe"), ("可执行文件", "*.exe"), ("全部", "*.*")])
        if p:
            self.ffmpeg_var.set(p)
            self._check_ffmpeg()
            self.log(f"ffmpeg 指定为：{p}")

    def on_start(self) -> None:
        if self.busy:
            return
        if not self.series or not self.line:
            messagebox.showinfo(APP_NAME, "请先解析地址并选择线路。")
            return
        eps = self.selected_episodes()
        if not eps:
            messagebox.showinfo(APP_NAME, "还没有勾选任何集数。")
            return
        out = self.out_dir.get().strip()
        if not out:
            messagebox.showinfo(APP_NAME, "请选择保存目录。")
            return
        fmt = self.fmt_var.get()
        if fmt == "mp4" and not core.find_ffmpeg(self.ffmpeg_var.get().strip()):
            if not messagebox.askyesno(
                    APP_NAME,
                    "没找到 ffmpeg，无法生成 MP4。\n是否继续（将只保存 .ts 原始流）？"):
                return
            fmt = "mkv"

        os.makedirs(out, exist_ok=True)
        opts = core.JobOptions(
            out_dir=out, fmt=fmt,
            workers=max(1, int(self.workers_var.get() or 16)),
            retries=5, drop_ads=self.drop_ads_var.get(),
            keep_segments=self.keep_seg_var.get(),
            ffmpeg=self.ffmpeg_var.get().strip(),
        )

        for e in eps:
            e.status = "排队中"
            self._refresh_row(e)

        self.cancel.clear()
        self.busy = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_parse.configure(state="disabled")
        self.pb_all.configure(value=0)
        self.pb_ep.configure(value=0)
        self.status_var.set(f"下载中 0 / {len(eps)}")
        self.log(f"===== 开始下载 {len(eps)} 集，格式 {fmt.upper()}，"
                 f"并发 {opts.workers} → {out} =====")

        job = core.Job(self.series, eps, opts,
                       on_log=self.bridge.log,
                       on_episode_progress=self._on_ep_progress,
                       on_overall=self.bridge.overall,
                       on_episode_done=self._on_ep_done,
                       cancel=self.cancel)
        self._job_eps = eps
        self._job = job

        def work():
            try:
                ok, fail = job.run()
                self.bridge.done(ok, fail)
            except Exception:  # noqa: BLE001
                self.bridge.error(traceback.format_exc())
                self.bridge.done(0, len(eps))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _on_ep_progress(self, idx: int, p) -> None:
        self.bridge.ep_progress(idx, p)

    def _on_ep_done(self, ep, ok: bool, msg: str) -> None:
        try:
            idx = self._job_eps.index(ep)
        except ValueError:
            idx = 0
        self.bridge.ep_done(idx, ok, msg)

    def on_stop(self) -> None:
        if not self.busy:
            return
        self.cancel.set()
        self.status_var.set("正在停止 …")
        self.log("已请求停止：当前分片下完就退出，已下载内容保留")

    # --------------------------------------------------------- 事件循环 #
    def _drain(self) -> None:
        try:
            while True:
                try:
                    m = self.q.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle(m)
                except Exception:  # noqa: BLE001
                    # 单条消息处理失败不能拖死整个消息泵
                    try:
                        self.log("处理消息出错：" + traceback.format_exc()[-800:])
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            self.after(80, self._drain)

    def _handle(self, m: Msg) -> None:
        if m.kind == "log":
            self.log(str(m.payload))
        elif m.kind == "series":
            self._apply_series(m.payload)
        elif m.kind == "error":
            self.info_var.set("出错了，详见下方日志")
            self.status_var.set("失败")
            self.btn_parse.configure(state="normal")
            self.log(f"✗ {m.payload}")
            messagebox.showerror(APP_NAME, str(m.payload)[:800])
        elif m.kind == "probe_row":
            p = m.payload
            if isinstance(p, tuple) and p and p[0] == "ff":
                self.ff_state.set(p[1])
                return
            if self.line:
                for e in self.line.episodes:
                    if e.nid == p:
                        self._refresh_row(e)
                        break
        elif m.kind == "ff_path":
            if not self.ffmpeg_var.get().strip():
                self.ffmpeg_var.set(str(m.payload))
        elif m.kind == "d_rows":
            d, title = m.payload
            self._d_fill(d.get("items") or [], title,
                         total=d.get("total", 0), page=d.get("page", 1),
                         pagecount=d.get("pagecount", 1))
            boards = d.get("boards") or []
            if boards:
                head = "  ".join(
                    f"{b.group}: {b.count}条/最高{b.top_value}" for b in boards)
                self.d_log(f"{title} → {head}")
            else:
                self.d_log(f"{title} → {len(d.get('items') or [])} 条")
        elif m.kind == "d_detail":
            self._d_apply_detail(m.payload)
        elif m.kind == "d_error":
            self._d_stat("出错了，详见下载页日志")
            self.d_log(f"✗ {m.payload}")
        elif m.kind == "d_idle":
            self._d_busy = False
            self._d_buttons("normal")
            pend = getattr(self, "_d_pending", None)
            self._d_pending = None
            if pend:
                self.after(30, lambda: self._d_worker(*pend))
        elif m.kind == "overall":
            done, total, label = m.payload
            self.overall_var.set(f"总进度  {done} / {total}    {label}")
            self.pb_all.configure(value=(done * 100 / total) if total else 0)
            if total:
                self.status_var.set(f"下载中 {min(done + 1, total)} / {total}")
        elif m.kind == "ep_progress":
            idx, p = m.payload
            if self.line and idx < len(self.line.episodes):
                ep = self.line.episodes[idx]
                self.ep_var.set(
                    f"{ep.label}   {p.percent:5.1f}%   {p.done}/{p.total} 段   "
                    f"{core.human_bytes(p.speed)}/s")
                self.pb_ep.configure(value=p.percent)
        elif m.kind == "ep_done":
            idx, ok, msg = m.payload
            if self.line and idx < len(self.line.episodes):
                ep = self.line.episodes[idx]
                ep.status = ("已完成" if ok else f"失败：{msg}")[:60]
                self._refresh_row(ep)
            self.pb_ep.configure(value=100 if ok else 0)
        elif m.kind == "done":
            ok, fail = m.payload
            self.busy = False
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.btn_parse.configure(state="normal")
            self.pb_ep.configure(value=0)
            self.ep_var.set("当前集  -")
            if self.cancel.is_set():
                self.status_var.set(f"已停止（成功 {ok}，失败/跳过 {fail}）")
                self.log(f"===== 已停止：成功 {ok}，失败 {fail} =====")
            else:
                self.status_var.set(f"全部结束（成功 {ok}，失败 {fail}）")
                self.overall_var.set(f"总进度  {ok + fail} / {ok + fail}    结束")
                self.pb_all.configure(value=100 if ok + fail else 0)
                self.log(f"===== 全部结束：成功 {ok}，失败 {fail} =====")
                if fail == 0:
                    messagebox.showinfo(APP_NAME, f"全部完成：{ok} 集已保存到\n{self.out_dir.get()}")
                else:
                    messagebox.showwarning(APP_NAME, f"完成 {ok} 集，{fail} 集失败。\n详见日志。")

    def _on_close(self) -> None:
        if self.busy and not messagebox.askyesno(
                APP_NAME, "正在下载，确定退出吗？\n已下载的分片会保留，下次可续传。"):
            return
        self.cancel.set()
        self.destroy()


# --------------------------------------------------------------------------- #
def enable_dpi() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:  # noqa: BLE001
                pass


def cli(argv: list[str]) -> int:
    """无界面下载：AGE下载器.exe --cli <播放页URL> [-n 集数] [-o 目录] [-f mp4|ts]

    供批处理/脚本调用，也用于验证打包版完整链路。进度写 cli.log。
    """
    import argparse
    import core as _c

    ap = argparse.ArgumentParser(prog="AGE下载器", add_help=False)
    ap.add_argument("url")
    ap.add_argument("-n", "--episodes", default="1",
                    help="集数，如 1、1-3、1,2,5（默认 1）")
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("-f", "--fmt", default="mp4", choices=["mp4", "mkv"])
    ap.add_argument("-w", "--workers", type=int, default=16)
    ap.add_argument("--keep-segments", action="store_true")
    ap.add_argument("--keep-ads", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        a = None
    lines: list[str] = []
    lock = __import__("threading").Lock()

    def log(s: str) -> None:
        with lock:
            lines.append(str(s))
            try:
                with open(os.path.join(_log_dir, "cli.log"), "a",
                          encoding="utf-8") as fh:
                    fh.write(str(s) + "\n")
            except Exception:  # noqa: BLE001
                pass

    _log_dir = (os.path.dirname(os.path.abspath(sys.executable))
                if getattr(sys, "frozen", False)
                else os.path.dirname(os.path.abspath(__file__)))
    if a is None:
        log("参数错误")
        return 2

    out_dir = a.out or os.path.join(os.path.expanduser("~"), "Downloads", "AGE动漫")
    os.makedirs(out_dir, exist_ok=True)

    sess = _c.make_session(_c.DEFAULT_UA, a.url)
    final, _cfg, html = _c.resolve_play_url(sess, a.url)
    series = _c.parse_series(html, final)
    log(f"剧名={series.title} aid={series.aid} 总集数={series.total_episodes}")
    line = series.lines[0]
    picked: list = []
    for tok in str(a.episodes).replace("，", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if "-" in tok:
            lo, hi = tok.split("-", 1)
            picked += [e for e in line.episodes
                       if int(lo) <= e.nid <= int(hi)]
        else:
            picked += [e for e in line.episodes if e.nid == int(tok)]
    seen, eps = set(), []
    for e in picked:
        if e.nid not in seen:
            seen.add(e.nid)
            eps.append(e)
    if not eps:
        log("没有选中任何集")
        return 2
    log(f"选中 {len(eps)} 集: {[e.label for e in eps]}")

    opts = _c.JobOptions(out_dir=out_dir, fmt=a.fmt, workers=a.workers,
                         drop_ads=not a.keep_ads,
                         keep_segments=a.keep_segments,
                         ffmpeg=_c.find_ffmpeg() or "")
    log(f"输出目录={out_dir} 格式={a.fmt} 并发={a.workers} ffmpeg={opts.ffmpeg}")
    job = _c.Job(series, eps, opts, on_log=log)
    ok, fail = job.run()
    log(f"结束: 成功 {ok} 失败 {fail}")
    for e in eps:
        log(f"  {e.label} {e.status} {e.saved_path}")
    return 0 if fail == 0 else 1


def selftest(argv: list[str]) -> int:
    """无界面自检：AGE下载器.exe --selftest <播放页URL>

    用来确认打包版能联网解析、能找到内置 ffmpeg；结果打印到控制台并写入
    selftest.txt（--noconsole 版没有 stdout，必须落盘）。
    """
    import core as _c

    url = argv[1] if len(argv) > 1 else "https://age001.com/play/12537-1-1.html"
    out: list[str] = []

    def p(s: str = "") -> None:
        out.append(str(s))

    p(f"{APP_NAME} v{APP_VER} 自检")
    p(f"frozen={getattr(sys, 'frozen', False)}  exe={sys.executable}")
    p(f"_MEIPASS={getattr(sys, '_MEIPASS', None)}")
    p("")
    ff = _c.find_ffmpeg()
    p(f"ffmpeg : {ff}")
    p(f"版本   : {_c.ffmpeg_version(ff) if ff else '(未找到)'}")
    p("")
    p(f"解析   : {url}")
    try:
        sess = _c.make_session(_c.DEFAULT_UA, url)
        final, cfg, html = _c.resolve_play_url(sess, url)
        p(f"  from={cfg.get('from')} encrypt={cfg.get('encrypt')}")
        series = _c.parse_series(html, final)
        p(f"  剧名={series.title} aid={series.aid} 总集数={series.total_episodes}")
        for ln in series.lines:
            p(f"  线路 {ln.sid} {ln.name}: {len(ln.episodes)} 集 "
              f"({ln.episodes[0].label} ~ {ln.episodes[-1].label})")
        ep = series.lines[0].episodes[0]
        pr = _c.probe_episode(sess, ep.play_url, drop_ads=True)
        pl = pr.playlist
        p(f"  第1集 m3u8: {pl.variant_url}")
        p(f"    {len(pl.segments)} 段 / {_c.human_time(pl.total_duration)} / "
          f"{pl.resolution or '?'} / {pl.bandwidth or 0}bps / "
          f"剔除广告块 {[(b.block, b.segs, round(b.duration, 1)) for b in pr.dropped]}")
        p(f"    末片: {pl.segments[-1].url}")
    except Exception as exc:  # noqa: BLE001
        p(f"  解析失败: {type(exc).__name__}: {exc}")

    # ---- 发现页（热门 / 搜索）自检 ----
    p("")
    p("发现页数据源：")
    try:
        import discover as _d
        ds = _d.site_session()
        for title, key in _d.SOURCES:
            try:
                d = _d.load_source(ds, key, 1)
                items = d.get("items") or []
                boards = d.get("boards") or []
                extra = ""
                if boards:
                    extra = " | " + " / ".join(
                        f"{b.group} {b.count}条" for b in boards)
                tot = d.get("total")
                p(f"  {title:<8} {len(items)} 条"
                  + (f" (total={tot})" if tot else "") + extra)
                if items:
                    p(f"      例: {items[0].name} [{items[0].year} "
                      f"{items[0].area}]")
            except Exception as exc:  # noqa: BLE001
                p(f"  {title:<8} 失败 {type(exc).__name__}: {exc}")
        r = _d.search_vods(ds, "命运", limit=200)
        p(f"  搜索「命运」: {len(r.get('items') or [])} 条 "
          f"(total={r.get('total')})")
        d1 = _d.fetch_detail(ds, vid=12537)
        it = d1.get("item")
        if it:
            p(f"  详情 12537: {it.name} / {it.year} / {it.area} / {it.lang}"
              f" / {it.remarks} / 播放链接 {len(d1.get('plays') or [])} 个")
    except Exception as exc:  # noqa: BLE001
        p(f"  发现页失败: {type(exc).__name__}: {exc}")

    text = "\n".join(out)
    # --noconsole 打包时 sys.stdout 为 None，直接 print 会抛 AttributeError
    written = ""
    try:
        pth = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                           "selftest.txt")
        with open(pth, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        written = pth
    except Exception as exc:  # noqa: BLE001
        written = f"(写入失败: {exc})"
    if sys.stdout:
        try:
            print(text)
            print(f"\n[已写入] {written}")
        except Exception:  # noqa: BLE001
            pass
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0].lower() in ("--selftest", "/selftest", "-t"):
        return selftest(argv)
    if argv and argv[0].lower() in ("--cli", "/cli"):
        return cli(argv[1:])
    enable_dpi()
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
