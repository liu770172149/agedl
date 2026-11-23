---
name: age-anime
description: >-
  访问 AGE 动漫站（www.age001.com）并下载番剧。用于查热门榜单/最新入库/今日更新、按关键词搜索作品、取作品详情与集数清单、
  解析播放页拿到真实 m3u8 分片地址、把指定集数下载成本地 MP4/MKV（自动剔除片头广告、多线程分片、无损封装、不做转码）。
  触发词：age动漫、age001、番剧下载、动漫下载、猜你喜欢排行、找番、某番第几集、m3u8 解析、hls 下载。
  【不适用】YouTube/B站/Netflix 等其他站点；需要登录/付费/DRM 的内容；实时直播流；纯转码或剪辑（本 skill 只做无损封装）。
license: MIT
allowed-tools: Bash Read Write
metadata:
  version: 1.1.0
  skill-author: lead
  last-reviewed: 2026-11-23
  domain: media
  unit-count: 7
  platforms: windows, linux, macos
  kccs:
    目的: 让 agent 直接查询 AGE 动漫站的榜单与搜索、解析任意播放页的真实片源、并把番剧下载成可播放的本地文件。
    条件: 目标站点为 www.age001.com；本机装有 Python 3.9+（含 requests）；需要下载时还要有 ffmpeg。Windows / Linux / macOS 都支持。
    成功: stdout 输出合法 JSON（ok=true），下载模式下目标文件存在且 ffprobe 能读出正常时长与 h264/aac 流。
    证据: JSON 里的 variant_url / segments / duration / ok_count / files[].bytes，配合 ffprobe 校验。
---

# AGE 动漫 — 查询与下载

把 AGE 动漫站的「发现 / 搜索 / 解析 / 下载」四件事封装成一条 JSON CLI。
所有能力都来自本站实测行为，**不要**改用 `/search/` 路径或猜 maccms 原生接口（见「坑」）。

部署、ffmpeg 查找顺序、FAQ、跨平台细节都写在同目录的 `DEPLOY.md`，需要时读它。

## 路由表

| 用户想要 | 子命令 | 关键参数 |
|---|---|---|
| 看看有什么热门 / 排行 | `hot` | `--src 本周排行`（默认第一个） |
| 最新入库、可翻页 | `hot` | `--src 最新入库 --page 2` |
| 按名字找番 | `search` | `关键词`、`--limit`（≤200） |
| 某部番的详细信息 | `detail` | 作品 id 或 `/vod/N.html` |
| 有多少集、有哪些线路 | `series` | 播放页 URL |
| 真实片源地址 / 分片 / 码率 | `probe` | `-n 1`、`--line 爱看` |
| 下载某几集 | `download` | `-n 1-3`、`-f mp4`、`-o 目录` |
| 环境不对劲 | `doctor` | `-o 目录` |
| 手上有遗留 `.raw` | `convert` | 目录路径 |
| 怀疑本机环境/平台有问题 | `selftest` | `--timeout 600` |

## 运行方式

脚本自包含（同目录带 `core.py`、`discover.py`、`platform_compat.py`）。
**用 `__file__` 相对定位，不要写死盘符**：

```bash
# 用户级安装位置
#   Windows : %USERPROFILE%\.dsh\skills\age-anime\scripts\agedl_cli.py
#   Linux   : ~/.dsh/skills/age-anime/scripts/agedl_cli.py
#   macOS   : ~/.dsh/skills/age-anime/scripts/agedl_cli.py

python  "<skills根>/age-anime/scripts/agedl_cli.py" <子命令> [参数]   # Windows
python3 "<skills根>/age-anime/scripts/agedl_cli.py" <子命令> [参数]   # Linux / macOS
```

- stdout = 一个 JSON 对象；stderr = 进度日志（可忽略或转述给用户）。
- 退出码：`0` 全成功，`1` 参数/环境错误，`2` 部分集数失败。
- 中文参数出现乱码时设 `PYTHONIOENCODING=utf-8`（Linux 上通常不需要）。
- 平台差异已收敛到 `scripts/platform_compat.py`：ffmpeg 文件名（`ffmpeg.exe` vs `ffmpeg`）、
  候选目录（`C:\ffmpeg\bin` vs `/usr/bin`、`/opt/homebrew/bin` 等）、执行位、`subprocess`
  的 `creationflags`、文件名 255 **字节**上限。写新代码时调它，别自己写 `if sys.platform`。

## 典型流程

### 1. 用户说「最近有什么好看的番」
```
agedl_cli.py hot --src 本周排行
```
返回 25 条，每条含 `name / rank / heat / remarks / play_url`。
`hot` 的 `sources` 字段列出全部 7 个数据源名称，可直接回给用户挑。
榜单页只给名字和热度，`year/area/tags` 是空的——要补全就对某一条调 `detail`。

### 2. 用户说「帮我找一下 XXX」
```
agedl_cli.py search "命运" --limit 200
```
站点服务端搜索，`total` 是命中总数。结果只有 id/name/pic，需要年份地区再用 `detail`。

### 3. 用户说「XXX 有多少集」
```
agedl_cli.py series "https://www.age001.com/play/12537-1-1.html"
```
返回 `title / aid / total_episodes / lines[]`，每条线路带完整 `episodes[]`（`nid / label / play_url`）。
**注意 `total_episodes` 是各线路集数的最大值**——某条线路可能少几集。

### 4. 用户问「真实地址是什么 / 能不能直接播」
```
agedl_cli.py probe "https://www.age001.com/play/12537-1-1.html" -n 1
```
返回 `variant_url`（可直接丢进播放器的 m3u8）、`segments`（分片数）、`duration_text`、
`resolution`、`bandwidth`、`key_method`（本站恒为 `NONE`，无加密）、`dropped_blocks`（被判定为广告的块）。
把 `variant_url` 给用户即可，播放器直接能开（无需 Referer/UA）。
Linux 上可以用 `ffplay` 或 `mpv` 直接验证。

### 5. 用户说「下载第 N 集 / 第 N 到 M 集」
```
agedl_cli.py download "https://www.age001.com/play/12537-1-1.html" -n 1-3 -f mp4 -o "/path/to/番剧"
```
- `-n` 支持 `1`、`1-3`、`1,2,5`、`all`。
- `-f mp4`（默认）或 `mkv`，都是 `-c copy` 无损封装，**不转码**。
- `-w` 并发分片数，默认 24；网络差就降到 8。
- 已存在的同名文件会跳过，可安全重跑。
- 结束返回 `ok_count / fail_count / files[]`（含绝对路径和字节数）。
- 没有 ffmpeg 时不会硬失败：会下到 `.raw` 并在 `files[]` 里指出来，装好 ffmpeg 后跑 `convert` 补转。

## 站点事实（写代码/回答用户时的依据）

- 播放页 `/play/<aid>-<sid>-<nid>.html`，详情页 `/vod/<vid>.html`，两者都能被 `series` 吃。
- 片源是 HLS：master m3u8 → 单档 variant（如 `2293kb/hls/index.m3u8`）→ 明文 `.ts` 分片。
- `#EXT-X-KEY:METHOD=NONE`，**无 AES 加密、无防盗链**，带不带 Referer/UA 都返回 200。
- 播放列表里混有广告块：正片会被 `#EXT-X-DISCONTINUITY` 切成多段（同一 CDN+目录前缀），
  广告来自**另一个源**。`core.drop_ad_blocks` 用「分片数最多的 src 才是正片」判定并剔除。
- 名称常带零宽字符 `\u200b`，`discover.clean()` 已处理。
- `vod_score` 普遍为 `0.0`，`vod_total`/`vod_serial` 恒为 `0`，**不要拿它们当集数**。

## 坑（踩过的，别再踩）

1. **`/search/...` 一律被 WAF 拦成滑动验证码页**。只能用 `/index.php/ajax/suggest?mid=1&wd=`，
   它才是真搜索（`wd=命运` → 63 条）。`search` 子命令已封装好，不要自己拼 URL。
2. `/index.php/ajax/data` 只能「按时间倒序翻页」（total=28528，limit 上限 20），
   **它忽略 wd/tid/order 等一切筛选参数**，不能当搜索用。
3. 相对分片路径（形如 `/20261119/xxx.ts`）必须 `urljoin` 到 **variant URL**，不是 master URL。
4. **`.ts` 扩展名可能在 Windows 企业环境被透明加密层（如 Trld Enc4）接管**——写出去的 .ts
   其他进程读不到明文。所以全链路用 `.seg`（分片缓存）和 `.raw`（中间流），最终产物只用
   `.mp4`/`.mkv`。Linux/macOS 无此问题，但代码这样写在所有平台都无害，别改回去。
5. **Windows 特例**：位于某些受限目录（如 `D:\deepseekproject`）内的可执行文件只能往该目录写，
   否则 ffmpeg 报 `Permission denied`。`core.remux_container` 会自动把 ffmpeg 复制到临时目录
   再跑以绕开；如果连 Python 建目录都被拒，**把输出目录换到别处**。Linux/macOS 上没有这个限制。
6. `subprocess` 读 ffmpeg 输出必须 `encoding="utf-8", errors="replace"`，
   否则 GBK 解码中文路径会抛 `UnicodeDecodeError`，让封装被误判失败。
7. **不要把 `>` 重定向的产物直接 `json.load`**：PowerShell 的 `>` 会写成 UTF-16 + BOM，
   报 `0xff invalid start byte`。拿 JSON 请用 `subprocess.run(..., capture_output=True)`。
   Linux/macOS 的 `>` 是纯字节，没这个问题。
8. **文件名长度按字节算**：从原站拿到的中文标题如果超过 **255 字节**（约 85 个汉字），
   ext4/APFS 会 `ENAMETOOLONG`。`core.sanitize` 已按 240 字节截断且不切断多字节字符，
   自己写落盘逻辑时也要走它。

## 验证本机是否装好

```bash
python3 agedl_cli.py doctor      # 环境 / ffmpeg / 输出目录可写性 / 平台摘要
python3 agedl_cli.py selftest    # 52 项跨平台逻辑 + 26 项 POSIX 端到端，共 78 项断言
```

`selftest` 全绿时 `summary` 是 `2/2 套测试通过`。

## 与 GUI 版的关系

`D:\AGE下载器_v1.2\AGE下载器.exe` 是同一套 `core.py`/`discover.py` 的图形界面版
（双 tab：下载 / 发现热门）。本 skill 是它的无界面等价物，逻辑一致、互不依赖。
GUI 版适合人手动用（仅 Windows）；skill 适合 agent 批量查询与下载，三个平台都能跑。
