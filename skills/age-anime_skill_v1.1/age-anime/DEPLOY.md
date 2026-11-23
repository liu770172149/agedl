# age-anime Skill — 部署与使用手册

> 面向「在别人的机器上装好并用起来」。
> 目标读者：要部署这个 skill 的人，以及第一次用它下番的 agent / 使用者。
> 版本 1.1.0 ｜ 最后验证 2026-11-23

---

## 0. 这东西是干什么的

把 AGE 动漫站（`www.age001.com`）的四类操作封装成一条 **JSON 命令行**，让 agent（或人）能：

- 查热门榜单、最新入库、今日更新、新番上架
- 按关键词搜索作品
- 解析任意播放页 → 剧名 / 线路 / 全部集数 / 真实 m3u8 地址
- 把指定集数下载成本地 **MP4 / MKV**（多线程分片、自动剔片头广告、无损封装不转码）

**它不是**：通用视频下载器、转码工具、YouTube/B站 下载器、能下 DRM/付费内容的东西。

---

## 1. 前置条件

### 1.1 必需

| 项目 | 要求 | 说明 |
|---|---|---|
| 操作系统 | Windows 10 / 11 ｜ Linux ｜ macOS | Windows 11 已实测完整下载；Linux/macOS 的平台逻辑有 78 项断言覆盖（见 §7），但尚未在真机上跑过完整在线下载 |
| Python | **3.9 或更高**（3.10+ 推荐） | 需要 `python`/`python3` 在 PATH 里，或记住它的绝对路径 |
| Python 包 | `requests` | 唯一运行时依赖 |
| 网络 | 能访问 `www.age001.com` 及其 CDN | 部分公司网/学校网会拦，见 §6.1 |

装 requests：

```bash
python -m pip install requests      # Windows
python3 -m pip install requests     # Linux / macOS
```

### 1.2 下载功能额外需要

| 项目 | 要求 |
|---|---|
| ffmpeg | 有 `ffmpeg`（Windows 上是 `ffmpeg.exe`）即可，下载版 / 便携版 / 包管理器装都行 |

**没有 ffmpeg 也能跑**：只会下载并合并出 `.raw` 中间流，不封装成 MP4。装好 ffmpeg 后再用 `convert` 子命令补转（见 §5.8）。

装 ffmpeg 的几种方式，任选其一：

```powershell
# Windows
winget install --id Gyan.FFmpeg      # 方式 A：winget（最省事）
scoop install ffmpeg                  # 方式 B：scoop
# 方式 C：直接下便携版，解压到任意目录
# https://github.com/BtbN/FFmpeg-Builds/releases  →  ffmpeg-master-latest-win64-gpl.zip
```

```bash
# Linux
sudo apt install ffmpeg       # Debian / Ubuntu
sudo dnf install ffmpeg       # Fedora / RHEL（需 RPM Fusion）
sudo pacman -S ffmpeg         # Arch

# macOS
brew install ffmpeg
```

> ⚠ **关键**：ffmpeg 的位置会被程序自动发现（见 §3）。放到奇怪的地方就设环境变量 `AGEDL_FFMPEG`，一劳永逸。

### 1.3 不需要

- ❌ 不需要装 `yt-dlp`、`N_m3u8DL-RE`、VLC、浏览器插件
- ❌ 不需要 GUI，不需要显示桌面
- ❌ 不需要管理员权限

---

## 2. 安装

### 2.1 确定 skill 目录

DSH 的 skill 搜索根按优先级依次是：

1. `<项目目录>/.dsh/skills/` ← 项目级，只对该项目生效
2. `<项目目录>/.agents/skills/`
3. 自定义目录（`customSkillDirs` 配置）
4. **`<dshHome>/skills/`** ← 用户级，所有项目都能用（推荐）
5. `<agentsHome>/skills/`
6. 内置目录

`<dshHome>` 默认是：

| 系统 | 路径 |
|---|---|
| Windows | `C:\Users\<你的用户名>\.dsh` |
| Linux / macOS | `~/.dsh` |

**所以用户级安装位置 = `C:\Users\<用户名>\.dsh\skills\age-anime\`（Linux/macOS 上是 `~/.dsh/skills/age-anime/`）**

只想给某个项目用，就放 `<项目目录>\.dsh\skills\age-anime\`。

### 2.2 拷贝文件

把整个 `age-anime` 目录拷进去。最终结构必须是：

```
<skills根>\age-anime\
├── SKILL.md                     ← 必需，frontmatter 必须合法
├── DEPLOY.md                    ← 本文档（可选，给人和 agent 查阅）
└── scripts\
    ├── agedl_cli.py             ← 命令行入口
    ├── core.py                  ← 站点解析 / 下载 / 封装
    ├── discover.py              ← 榜单 / 搜索 / 详情
    ├── platform_compat.py       ← 跨平台差异
    ├── test_platform.py         ← 52 项逻辑断言
    └── test_posix_sim.py        ← 26 项 POSIX 端到端断言
```

Windows（PowerShell）：

```powershell
$dest = "C:\Users\$env:USERNAME\.dsh\skills"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Path ".\age-anime" -Destination $dest -Recurse -Force
Remove-Item "$dest\age-anime\scripts\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
```

Linux / macOS：

```bash
DEST="${DSH_HOME:-$HOME/.dsh}/skills"
mkdir -p "$DEST"
cp -R ./age-anime "$DEST/"
find "$DEST/age-anime" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$DEST/age-anime" -name '*.pyc' -delete
```

或者直接用附录 B（Windows）/ 附录 B2（Linux·macOS）的一键脚本。

**注意**：
- 目录名随便叫，但 `SKILL.md` 里的 `name` 字段必须是 kebab-case（`age-anime`），且与目录名一致更不容易出岔子。
- 如果源目录里有 `scripts\__pycache__\`，**不要拷过去**——那是原机器 Python 版本的字节码，换机器会干扰。
- 层级不能超过两层：`skills/age-anime/SKILL.md` ✅；`skills/age-anime/sub/SKILL.md` ❌（不会被发现）。

### 2.3 验证安装成功

```bash
cd ~/.dsh/skills/age-anime/scripts     # Windows: C:\Users\<用户名>\.dsh\skills\age-anime\scripts
python agedl_cli.py doctor             # Linux/macOS 用 python3
```

期望输出（字段值随机器不同）：

```json
{
  "ok": true,
  "python": "3.14.3",
  "executable": "C:\\Python314\\python.exe",
  "platform": {
    "platform": "win32",
    "os_name": "nt",
    "is_windows": true,
    "is_linux": false,
    "is_macos": false,
    "path_sep": "\\",
    "max_name_bytes": 240
  },
  "ffmpeg": "C:\\ffmpeg\\bin\\ffmpeg.exe",
  "ffmpeg_version": "ffmpeg version 7.1 ...",
  "ffmpeg_executable": true,
  "out_dir": "C:\\Users\\you\\Downloads\\AGE动漫",
  "out_writable": true,
  "hint": ""
}
```

逐项检查：
- `ok: true` — 脚本能跑
- `python` — 版本 ≥ 3.9
- `platform.is_windows` / `is_linux` / `is_macos` — 三个里恰好一个为 `true`，对得上你的机器
- `ffmpeg` 不是 `null` — 找到了。若是 `null`，看 §3
- `ffmpeg_executable: true` — 有执行权限（Linux/macOS 上会检查 `+x`）
- `out_writable: true` — 默认输出目录可写

> 如果想连跨平台逻辑一起验收，跑 `python agedl_cli.py selftest`，
> 期望 `"summary": "2/2 套测试通过"`（详见 §7.6）。

### 2.4 验证 skill 被 DSH 识别

重启 DSH（或新开一个会话），看 skill 目录里有没有出现 `age-anime`。

也可以在新会话里直接说：「用 age-anime skill 看看本周排行」。agent 应该会自动加载它。

如果没被识别，按这个顺序查：
1. `SKILL.md` 是否存在且**开头就是** `---`（不能有空行或 BOM）
2. `name:` 和 `description:` 两个字段是否都在
3. `name` 是否是 kebab-case（只能小写字母、数字、连字符）
4. 层级是否超过两层
5. DSH 启动日志里有没有 `skill file ... ignored: ...` 的告警

---

## 3. ffmpeg 的查找顺序

程序按这个顺序找 ffmpeg（Windows 上是 `ffmpeg.exe`），命中即停：

1. 命令行 `--ffmpeg "路径"` 显式指定
2. **环境变量 `AGEDL_FFMPEG`** ← 换机器最省事的做法
3. `scripts/` 目录本身
4. `scripts/../`（即 `age-anime/`）
5. `age-anime/ffmpeg/`、`age-anime/ffmpeg/bin/`、`age-anime/bin/`
6. `age-anime/tools/`、`age-anime/tools/ffmpeg/bin/`
7. 向上三层各自找 `ffmpeg/`、`ffmpeg/bin/`、`bin/`、`tools/ffmpeg/bin/`（源码运行时）
8. PyInstaller 打包时的 `_internal/ffmpeg/`、`_MEIPASS`（仅 exe 版）
9. **平台标准位置** —— 由 `platform_compat.ffmpeg_candidate_dirs()` 给出：
   - Windows：`C:\ffmpeg\bin`、`C:\ProgramData\chocolatey\bin`、`~\scoop\shims`、WinGet Links
   - Linux：`/usr/bin`、`/usr/local/bin`、`/bin`、`/snap/bin`、`~/.local/bin`、`~/bin`、`~/ffmpeg/bin`
   - macOS：`/opt/homebrew/bin`（Apple Silicon）、`/usr/local/bin`、`/usr/local/opt/ffmpeg/bin`、`/opt/local/bin`（MacPorts）、`/opt/ffmpeg/bin`
   - 环境变量 `AGEDL_FFMPEG_DIR` **排在这一组的最前面**
10. **系统 PATH** 里的 `ffmpeg`（`shutil.which`）

找到之后，Linux/macOS 上会自动补 `+x` 执行位（从 zip 解压出来的二进制通常没有）。

最稳妥的两种做法：

```powershell
# Windows：设环境变量（永久）
[Environment]::SetEnvironmentVariable("AGEDL_FFMPEG", "C:\ffmpeg\bin\ffmpeg.exe", "User")
# 设完要新开终端才生效
```

```bash
# Linux / macOS：写进 shell 配置
echo 'export AGEDL_FFMPEG=/opt/ffmpeg/bin/ffmpeg' >> ~/.bashrc   # 或 ~/.zshrc
```

```bash
# 或者：直接放进 skill 目录（两个平台都是这条路径规则）
cp /path/to/ffmpeg ~/.dsh/skills/age-anime/scripts/ffmpeg
# Windows: Copy-Item "C:\ffmpeg\bin\ffmpeg.exe" "$env:USERPROFILE\.dsh\skills\age-anime\scripts\"
```

> 💡 便携分发场景：把 `ffmpeg`（和 `ffprobe`）一起放到 `age-anime/scripts/` 下，
> 整个 skill 就是一个自包含目录，拷到哪都能用（约 +165 MB / 双份约 +340 MB）。

---

## 4. 给 agent 用的方式

### 4.1 触发词

对话里说到这些词，agent 会自动加载本 skill：

> age动漫、age001、番剧下载、动漫下载、排行、找番、某番第几集、m3u8 解析、hls 下载

### 4.2 建议的提示词

| 你想干什么 | 直接说 |
|---|---|
| 看热门 | 「AGE 上现在什么最火」 |
| 看最新 | 「AGE 最近更新了哪些番」 |
| 找番 | 「在 AGE 上搜一下斗破苍穹」 |
| 查集数 | 「这个番一共几集：https://www.age001.com/play/12537-1-1.html」 |
| 要真实地址 | 「帮我把这集的 m3u8 地址找出来」 |
| 下载 | 「把命运奇异赝品第 1 到 3 集下到 /path/to/番剧」 |

### 4.3 CLI 的调用契约（agent 必读）

```bash
python  "<skills根>/age-anime/scripts/agedl_cli.py" <子命令> [参数]   # Windows
python3 "<skills根>/age-anime/scripts/agedl_cli.py" <子命令> [参数]   # Linux / macOS
```

- **stdout 永远是单个 JSON 对象**，直接 `json.loads()` 即可
- **stderr 是进度日志**，可以忽略，也可以转述给用户
- **退出码**：`0` 全成功 / `1` 参数或环境错误 / `2` 部分集数失败

**拿 JSON 的正确姿势**（Python）：

```python
import json, os, subprocess, sys

CLI = os.path.expanduser("~/.dsh/skills/age-anime/scripts/agedl_cli.py")
p = subprocess.run([sys.executable, CLI, "hot", "--src", "总排行"],
                   capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
data = json.loads(p.stdout)
```

用 `sys.executable` 而不是写死解释器路径，这样 Windows / Linux / macOS 的代码是同一份。

**错误示范**：

```powershell
# ❌ 不要用 PowerShell 的 > 重定向
python agedl_cli.py hot > hot.json
```

原因：PowerShell 的 `>` 默认写成 **UTF-16 LE + BOM**，下游 `json.load()` 会报
`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0`。
非要重定向就用 `| Out-File -Encoding utf8`。

Linux / macOS 的 `>` 是纯字节重定向，不会加 BOM，可以放心用：

```bash
python3 agedl_cli.py hot > hot.json && python3 -c "import json;json.load(open('hot.json'))"
```

---

## 5. 子命令参考

### 5.1 `doctor` — 环境自检

```bash
python agedl_cli.py doctor
python agedl_cli.py doctor -o "/path/to/番剧"   # Windows 写 /path/to/番剧     # 顺便检查指定目录可写性
```

### 5.2 `hot` — 热门 / 榜单 / 最新

```bash
python agedl_cli.py hot                          # 默认第一个源（本周排行）
python agedl_cli.py hot --src 总排行
python agedl_cli.py hot --src 最新入库 --page 3   # 只有这个源能翻页
```

7 个数据源：

| 名称 | 内容 | 条数 |
|---|---|---|
| `本周排行` | 本周动画排行榜 | 25（带排名+热度） |
| `本月排行` | 本月动画排行榜 | 25 |
| `总排行` | 动画总排行榜 | 25 |
| `最新入库` | 按时间倒序全站 | 每页 20，**共 28528 条 / 1427 页** |
| `今日更新` | 今天更新的番 | 24 |
| `新番上架` | 新番列表 | 24 |
| `首页更新` | 首页「最新更新」栏 | 84 |

返回结构：

```json
{
  "ok": true,
  "source": "总排行",
  "key": "rank:总",
  "page": 1, "pagecount": 1, "total": 25, "count": 25,
  "boards": [{"group": "动画总排行榜", "count": 25, "top_value": 45662, "avg_value": 15704.4}],
  "items": [{
    "vid": 31149, "name": "斗破苍穹剧场版 双帝之战",
    "year": "2026", "area": "大陆", "remarks": "正片", "tags": "动作,动画,奇幻",
    "heat": 986, "rank": 1, "updated": "2026-11-23 12:30:02",
    "detail_url": "https://www.age001.com/vod/31149.html",
    "play_url": "https://www.age001.com/play/31149-1-1.html",
    "pic": "https://p.bfp261112.com/upload/..."
  }],
  "sources": ["本周排行", "本月排行", "总排行", "最新入库", "今日更新", "新番上架", "首页更新"]
}
```

> ⚠ 榜单类数据源的 `year/area/lang/tags` 是**空的**（榜单页本身不提供）。
> 需要这些字段就对具体条目调 `detail`。

### 5.3 `search` — 关键词搜索

```bash
python agedl_cli.py search "命运"
python agedl_cli.py search "斗破苍穹" --limit 50
```

- `--limit` 上限 200（服务端硬限）
- `total` 是命中总数，`count` 是本次返回数

```json
{
  "ok": true, "keyword": "命运", "total": 63, "count": 50,
  "items": [{"vid": 26187, "name": "命运分叉后，我活成了心尖宠",
             "detail_url": "https://www.age001.com/vod/26187.html",
             "play_url": "https://www.age001.com/play/26187-1-1.html", "pic": "..."}]
}
```

搜索接口只返回 `id/name/pic`，其余字段为空——要详情得调 `detail`。

### 5.4 `detail` — 作品详情

```bash
python agedl_cli.py detail 12537
python agedl_cli.py detail "https://www.age001.com/vod/12537.html"
```

```json
{
  "ok": true,
  "item": {"vid": 12537, "name": "命运奇异赝品", "year": "2024", "area": "日本",
           "remarks": "全13集", "tags": "动作,动画,奇幻,日本动漫", "updated": "2026-03-30"},
  "kvs": {"发行地区": "日本", "主要演员": "花泽香菜,小野友树,...",
          "制作导演": "榎户骏,坂詰嵩仁", "语言对白": "日语", "播放状态": "全13集"},
  "play_count": 25,
  "plays": ["https://www.age001.com/play/12537-1-1.html", "..."]
}
```

> ⚠ **不要**用 `vod_score` / `vod_total` / `vod_serial` 判断集数——本站这几个字段恒为 `0`。
> 集数以 `series` 子命令的输出为准。

### 5.5 `series` — 解析集数与线路

```bash
python agedl_cli.py series "https://www.age001.com/play/12537-1-1.html"
```

支持播放页 `/play/<aid>-<sid>-<nid>.html` 和详情页 `/vod/<vid>.html` 两种输入。

```json
{
  "ok": true, "title": "命运奇异赝品", "aid": 12537, "total_episodes": 13,
  "lines": [
    {"sid": 1, "name": "爱看", "count": 12,
     "episodes": [{"nid": 1, "label": "第01集", "play_url": "https://www.age001.com/play/12537-1-1.html"}]},
    {"sid": 2, "name": "魔都", "count": 13, "episodes": [...]}
  ]
}
```

> ⚠ `total_episodes` 取的是**各线路集数的最大值**。某条线路可能少几集
> （上例「爱看」只有 12 集，「魔都」有 13 集）。

### 5.6 `probe` — 探测真实片源

```bash
python agedl_cli.py probe "https://www.age001.com/play/12537-1-1.html" -n 1
python agedl_cli.py probe "https://www.age001.com/play/12537-1-1.html" -n 1 --line 魔都
python agedl_cli.py probe "https://www.age001.com/play/12537-1-1.html" -n 1,3,5
```

```json
{
  "ok": true, "title": "命运奇异赝品", "aid": 12537,
  "line": {"sid": 1, "name": "爱看", "count": 12},
  "probed": [{
    "nid": 1, "label": "第01集",
    "variant_url": "https://bfikuncdn.com/20260111/l48XZxrI/2293kb/hls/index.m3u8",
    "segments": 740, "duration": 1479.7, "duration_text": "24:39",
    "bandwidth": 2293000, "resolution": "1920x1080",
    "key_method": "NONE",
    "dropped_blocks": [{"block": 1, "segs": 6, "duration": 17.6, "src": "bfikuncdn.com/20261119/VD50zTBF"}],
    "first_segment": "https://kkzycdn.com:65/20260111/l48XZxrI/2293kb/hls/dfv5Cp77.ts",
    "last_segment": "...",
    "estimate_bytes": 423940736, "estimate_text": "404.3 MB"
  }]
}
```

**`variant_url` 直接丢进播放器就能播**——本站无 DRM、无 AES、无防盗链，不需要 Referer 或特殊 UA。

### 5.7 `download` — 下载

```powershell
# 下第 1 集
python agedl_cli.py download "https://www.age001.com/play/12537-1-1.html" -n 1

# 下第 1-3 集到指定目录
python agedl_cli.py download "https://www.age001.com/play/12537-1-1.html" -n 1-3 -o "/path/to/番剧"   # Windows 写 /path/to/番剧

# 下全部（13 集）
python agedl_cli.py download "https://www.age001.com/play/12537-1-1.html" -n all -f mkv -w 8

# 指定线路 + 保留广告 + 保留分片缓存
python agedl_cli.py download "https://..." -n 5 --line 魔都 --keep-ads --keep-segments
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `-n / --episodes` | `1` | `1` / `1-3` / `1,2,5` / `all` |
| `-f / --fmt` | `mp4` | `mp4` 或 `mkv`，都是 `-c copy` 无损封装 |
| `-o / --out` | `~/Downloads/AGE动漫` | 输出目录，不存在会自动建 |
| `-w / --workers` | `24` | 并发分片数，1–64。网络差就降到 8 |
| `-r / --retries` | `5` | 单分片重试次数 |
| `--line` | 自动 | 线路名（如 `爱看`）或 sid（如 `1`） |
| `--keep-ads` | 关 | 保留片头广告块 |
| `--keep-segments` | 关 | 保留分片缓存目录 `_segs` |
| `--ffmpeg` | 自动 | ffmpeg.exe 路径 |

**线路自动选择规则**（不指定 `--line` 时）：
> 先按最大的线路集数算出要哪些集号 → 在「包含这批集号的全部线路」里取页面顺序第一条 → 没有线路包含全部集号时，退回集数最多的那条。

效果：下第 01 集走主线路（码率高），下第 13 集自动切到有第 13 集的那条。

返回：

```json
{
  "ok": true, "title": "命运奇异赝品",
  "line": {"sid": 1, "name": "爱看"},
  "fmt": "mp4", "out_dir": "D:\\番剧",
  "requested": 1, "ok_count": 1, "fail_count": 0, "elapsed": 60.7,
  "files": [{"nid": 2, "label": "第02集", "status": "已完成",
             "path": "D:\\番剧\\命运奇异赝品 第02集.mp4", "bytes": 327851247}]
}
```

**已存在的同名文件会自动跳过**，所以同一命令可以安全重跑（断点续传靠这个）。

### 5.8 `convert` — 把遗留 `.raw` 补转成 MP4

有些情况下下载会只留下 `.raw` 中间流（机器上没有 ffmpeg，或封装失败）。装好 ffmpeg 后：

```bash
python agedl_cli.py convert "/path/to/番剧"
python agedl_cli.py convert "/path/to/番剧" --keep    # 转换后保留 .raw
```

- 目录下所有 `*.raw` 逐个转 mp4
- 目标 mp4 已存在且非空 → 跳过
- 默认转换成功后删除 `.raw`

---

## 6. 常见问题

### 6.1 网络连不上站点

```
Error: HTTPSConnectionPool(host='www.age001.com', port=443): Read timed out
```

- 该站点在国内可直连。连不上先换网络（手机热点试一下）。
- 如果在公司/学校网，可能有 SNI 过滤，用手机热点验证一下。
- 站点偶发 502，重试即可。

### 6.2 `ffmpeg` 显示 `null`

doctor 的 `ffmpeg` 字段是 `null` 说明没找到。按 §3 的顺序排查，最快的办法：

```powershell
# 先确认 ffmpeg 本身能跑
ffmpeg -version

# 能跑就把它设成环境变量
[Environment]::SetEnvironmentVariable("AGEDL_FFMPEG", (Get-Command ffmpeg).Source, "User")
```

### 6.3 下载完成但只有 `.raw`，没有 `.mp4`

两个可能：

1. **没装 ffmpeg** — 这是设计行为，装好后 `convert` 补转（§5.8）
2. **ffmpeg 写盘被拒** — stderr 里会出现 `Permission denied` 或 `Error opening output`。
   见 §6.4。

### 6.4 `Permission denied` / `Error opening output`

这是**本机安全策略**导致的（已在一台装了透明加密 + DLP 的机器上复现）：

> 某些安全驱动会按「**可执行文件自身所在的路径前缀**」限制写盘范围。
> 位于 `D:\某些目录` 下的 ffmpeg 只能往该目录写。

程序的应对：`core.remux_container` 检测到 `Permission denied` 时，会**自动把 ffmpeg 复制到 `%TEMP%\agedl_ffbin\` 再重试**，通常就通了。

如果还是不行，手动验证：

```powershell
# 直接测 ffmpeg 能不能往目标目录写
& "C:\ffmpeg\bin\ffmpeg.exe" -f lavfi -i testsrc=d=1 -y "/path/to/番剧\_probe.mp4"
```

报错就说明那条路径被策略挡了。解决办法：
- 输出目录换到 `%TEMP%`、`%USERPROFILE%\Downloads` 这类常规位置
- 或把 ffmpeg 复制到目标盘根目录附近（如 `D:\ffmpeg\bin\`）再试

### 6.5 下载出来的视频播放器打不开

**先确认扩展名不是 `.ts`**。某些机器的透明加密驱动（如 "Trld Enc4"）会接管 `.ts` 扩展名，
写出去的 `.ts` 其他进程读到的是密文。本 skill 全链路**不用 `.ts`**（分片缓存用 `.seg`，
中间流用 `.raw`，成品只用 `.mp4`/`.mkv`），所以正常不会有这个问题。

验证文件是否真好的：

```powershell
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height `
        -of default=noprint_wrappers=1 "/path/to/番剧\xxx.mp4"

# 全片解码校验（0 错误才算过）
ffmpeg -v error -i "/path/to/番剧\xxx.mp4" -f null -
```

正常应当看到 `codec_name=h264` + `codec_name=aac`，第二条命令**没有任何输出且退出码为 0**。

### 6.6 搜索没结果 / 报验证码

**不要**自己拼 `/search/...` URL —— 那个路径被 WAF 拦成滑动验证码页。
搜索必须走 `/index.php/ajax/suggest`，`search` 子命令已经封装好了。

如果 `search` 也拿不到结果：
```powershell
# 直接验证接口本身
python -c "import sys; sys.path.insert(0,'.'); import discover; print(discover.search_vods(None,'命运',limit=10)['total'])"
```

### 6.7 下载很慢

- `-w` 从 24 降到 8 试试（并发太高反而被 CDN 限速）
- 换线路：`--line 魔都`（1.5 Mbps，更稳但画质低）
- 确认不是自己的带宽打满了

### 6.8 JSON 解析报 `0xff invalid start byte`

PowerShell 的 `>` 重定向写成了 UTF-16。改用 Python 的 `subprocess` 捕获 stdout，
或 `| Out-File -Encoding utf8`。见 §4.3。

### 6.9 中文乱码

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

或者用 `chcp 65001` 切到 UTF-8 代码页。

---

## 7. Linux / macOS

### 7.1 结论

**可以直接用。** 平台差异已经收敛到 `scripts/platform_compat.py` 一个文件里，
其它模块只调它，不再各自判断 `sys.platform`。三处原本会真的坏掉的地方都改掉了：

| 原来的问题 | 后果 | 现在的做法 |
|---|---|---|
| `sanitize()` 按**字符数**截到 110 | 中文 UTF-8 每字 3 字节 → 最长 330 字节，**超过 ext4/APFS 的 255 字节上限，写文件时 ENAMETOOLONG** | `safe_filename()` 先按字符截，再按**字节**截到 240，且不切断多字节序列 |
| `candidate_ffmpeg_dirs()` 全是 `C:\...` | Linux 上永远找不到 ffmpeg | 按平台给候选：`/usr/bin`、`/usr/local/bin`、`/bin`、`/snap/bin`、`/opt/homebrew/bin`、`/usr/local/opt/ffmpeg/bin`、`/opt/local/bin`、`~/.local/bin`、`~/bin`、`~/ffmpeg/bin` |
| `shutil.which("ffmpeg.exe")` | Linux 上永远 None | 用 `exe_names()` 取当前平台的候选名 |
| `creationflags=CREATE_NO_WINDOW` | Linux 上属性不存在 | `spawn_kwargs()` 按平台返回，Linux/macOS 返回 `{}` |
| zip 解压出来的 ffmpeg 无 `+x` | `PermissionError: [Errno 13]` | `ensure_executable()` 在 POSIX 上补 `S_IXUSR\|S_IXGRP\|S_IXOTH`，找到 ffmpeg 后自动调用 |

### 7.2 安装（Linux）

```bash
# 1) Python 与依赖
python3 --version            # 需要 3.9+
python3 -m pip install requests

# 2) ffmpeg（三选一）
sudo apt install ffmpeg      # Debian / Ubuntu
sudo dnf install ffmpeg      # Fedora / RHEL（需 RPM Fusion）
sudo pacman -S ffmpeg        # Arch

# 3) 放进 skill 目录（用户级）
mkdir -p ~/.dsh/skills
cp -r age-anime ~/.dsh/skills/
find ~/.dsh/skills/age-anime -name __pycache__ -type d -exec rm -rf {} +

# 4) 自检
cd ~/.dsh/skills/age-anime/scripts
python3 agedl_cli.py doctor
```

`doctor` 里这几项需要是 `true`：

```json
{
  "ok": true,
  "platform": { "is_linux": true, "path_sep": "/", "max_name_bytes": 240 },
  "ffmpeg": "/usr/bin/ffmpeg",
  "ffmpeg_executable": true,
  "out_writable": true
}
```

### 7.3 安装（macOS）

```bash
# Apple Silicon 走 /opt/homebrew，Intel 走 /usr/local
brew install ffmpeg python3

mkdir -p ~/.dsh/skills
cp -r age-anime ~/.dsh/skills/
find ~/.dsh/skills/age-anime -name __pycache__ -type d -exec rm -rf {} +

cd ~/.dsh/skills/age-anime/scripts
python3 agedl_cli.py doctor
```

macOS 的首次运行可能弹「无法验证开发者」，在
`系统设置 → 隐私与安全性` 里点「仍要打开」即可；或者先跑一次
`xattr -dr com.apple.quarantine ~/.dsh/skills/age-anime`。

### 7.4 ffmpeg 不在 PATH 上时

两个办法，任选：

```bash
# A. 环境变量（脚本会优先读它）
export AGEDL_FFMPEG=/opt/ffmpeg/bin/ffmpeg
export AGEDL_FFMPEG_DIR=/opt/ffmpeg/bin

# B. 直接把二进制放进 skill 目录（脚本会自动找到并补 +x）
cp /path/to/ffmpeg ~/.dsh/skills/age-anime/scripts/ffmpeg
```

写进 `~/.bashrc` 或 `~/.zshrc` 可以持久化。

### 7.5 平台差异对照

| 项目 | Windows | Linux | macOS |
|---|---|---|---|
| ffmpeg 文件名 | `ffmpeg.exe` | `ffmpeg` | `ffmpeg` |
| skill 目录 | `%USERPROFILE%\.dsh\skills` | `~/.dsh/skills` | `~/.dsh/skills` |
| 默认输出目录 | `%USERPROFILE%\Downloads\AGE动漫` | `~/Downloads/AGE动漫` | `~/Downloads/AGE动漫` |
| 文件名非法字符 | `\ / : * ? " < > \|` 全清 | 只清控制字符与 `/`（但冒号也清，便于跨系统拷贝） | 同 Linux，额外清 `:` |
| 单文件名字节上限 | 255 字符（UTF-16 计） | **255 字节** | **255 字节** |
| 保留设备名 | `CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9` | 无此概念 | 无此概念 |
| 子进程隐藏窗口 | `CREATE_NO_WINDOW` | 不适用 | 不适用 |
| 可执行权限 | 无此概念 | 需 `+x` | 需 `+x` |
| 路径分隔符 | `\` | `/` | `/` |
| 透明加密层问题（`.ts`/`%APPDATA%`） | 有（本机特例） | 无 | 无 |

> **注意**：`.ts` 扩展名被加密层接管、`D:\deepseekproject` 内可执行文件写入受限，
> 这两条都是**本机 Windows 环境的特例**，Linux 上不存在。但代码里的规避
> （全链路用 `.seg`/`.raw`、必要时把 ffmpeg 复制到临时目录重试）在
> 所有平台都无害，所以保留了。

### 7.6 怎么验证跨平台正确性（不需要真 Linux）

`scripts/` 下有两套测试，加起来 78 项断言：

```bash
python3 agedl_cli.py selftest          # 一次跑两套
```

或单独跑：

```bash
python3 test_platform.py     # 52 项：纯逻辑，不需要网络、不需要 ffmpeg
python3 test_posix_sim.py    # 26 项：POSIX 端到端，需要 ffmpeg
```

- **`test_platform.py`**：每个函数都接受显式 `platform=` 参数，所以可以在任何
  宿主上断言「如果这里是 Linux，候选路径应该是什么」。最后一组用
  `sys.platform = "linux"` + `importlib.reload(platform_compat)` 把模块级常量
  也真的切过去，验证 `WINDOWS=False`、`LINUX=True`、`spawn_kwargs()=={}`，
  之后 `finally` 恢复。这是**真执行**，不是看代码猜。
- **`test_posix_sim.py`**：在真实文件系统上创建一个 240 字节的中文名文件、
  跑一遍 `remux_container`（`.raw` → `.mp4` → `.mkv`）、验证全片解码零错误、
  验证含空格/中文/方括号/括号的路径能正常处理。

输出样例（Windows 宿主，两套全绿）：

```
→ 结果：52 项全部通过（0 失败）
→ 结果：26 项通过 / 0 失败 / 0 跳过
2/2 套测试通过
```

### 7.7 已知的平台差异风险（诚实说明）

1. **没有在真 Linux 上跑过完整的在线下载。** 上面两套测试覆盖的是
   「文件名规则、路径候选、子进程参数、执行位、以及一次真实的分片合并+封装」，
   但**没有**在 Linux 上真的连过 age001.com 下载一集。
   网络栈（`requests`）是跨平台的，风险很低，但这不是零。
   第一次在 Linux 上使用时，建议先跑：
   ```bash
   python3 agedl_cli.py probe -u "https://www.age001.com/play/12537-1-1.html" -n 1
   ```
   能出 JSON 就说明网络与解析都通。
2. **`%APPDATA%` / `.ts` 加密层**是 Windows 本机特例，Linux 上没有；但如果你在
   另一台装了企业 DLP 的 Windows 上部署，仍可能遇到「ffmpeg 写不出去」，
   这时 `core.remux_container` 会自动把 ffmpeg 复制到临时目录重试，
   stderr 会打一行「检测到写权限被限制，改用临时目录里的 ffmpeg 副本重试」。
3. **文件名大小写**：Linux 区分大小写，Windows 不区分。如果目标目录里已有
   `第01集.MP4`，再下 `第01集.mp4` 在 Linux 上会被当成两个文件。
   本 skill 生成的扩展名固定小写，正常不会撞。

---

## 8. 内部实现备忘（改代码时看）

### 8.1 文件职责

| 文件 | 职责 | 依赖 |
|---|---|---|
| `core.py` | 播放页解析、HLS playlist 解析、广告剔除、分片下载、合并、封装 | requests + platform_compat |
| `discover.py` | 榜单/卡片/搜索/详情解析 | requests |
| `platform_compat.py` | 跨平台差异：可执行文件名、ffmpeg 候选目录、文件名字节上限、子进程参数、执行位 | 仅标准库 |
| `agedl_cli.py` | 子命令分发、参数处理、JSON 输出 | core + discover + platform_compat |
| `test_platform.py` | 52 项跨平台逻辑断言（不打网络、不需要 ffmpeg） | platform_compat + core |
| `test_posix_sim.py` | 26 项 POSIX 端到端断言（会用真实 ffmpeg 跑一次封装） | platform_compat + core |

除 `platform_compat.py` 外，**没有任何模块写 `if sys.platform == ...`**。要支持新平台，
只改 `platform_compat.py` 里的 `exe_names()` 与 `ffmpeg_candidate_dirs()` 即可。

全部是纯函数 + dataclass，**没有全局状态**（`escaped_ffmpeg` 有一个锁与缓存路径，
但幂等），可以放心在长驻进程里反复调用。


### 8.2 站点结构要点

- 播放页 `/play/<aid>-<sid>-<nid>.html`，内联 `var player_aaaa={...}`（`encrypt:0` 即明文）
- 线路名在 `<ul class="menu0 title" id="menu0"><li>爱看</li><li>魔都</li></ul>`
- 集数列表在多个 `<div class="movurl mod"><ul><li><a href="/play/...">…</a></li></ul></div>`，
  **按线路顺序与 menu0 的 li 一一对应**
- 卡片用 `<li class="anime_icon1|2">`，真实图片在 `data_src` 属性（`src` 恒为 loading.gif）
- 榜单条目是 `<li class="rank_text">`，分组标题是 `<p class="dm-p">`

### 8.3 HLS 与广告

- master m3u8 → 单档 variant（如 `2293kb/hls/index.m3u8`）→ 明文 `.ts` 分片
- `#EXT-X-KEY:METHOD=NONE` — 无 AES
- **广告混在 playlist 里**：正片会被 `#EXT-X-DISCONTINUITY` 切成多块，
  但同属一个 CDN + 目录前缀；广告来自**另一个源**。
  `core.drop_ad_blocks` 的判据是「分片数最多的 src 才是正片」，其余块剔除。
- 相对分片路径（形如 `/20261119/xxx.ts`）必须 `urljoin` 到 **variant URL**，不是 master URL

### 8.4 数据坑

- 名称常带零宽字符 `\u200b` → `discover.clean()` 已处理
- `vod_score` 普遍 `0.0`，`vod_total`/`vod_serial` 恒 `0`，**不能当集数**
- `/index.php/ajax/data` 忽略 `wd`/`tid`/`order` 等一切筛选参数，只能时间倒序翻页
- `/index.php/ajax/suggest` 的 `page` 参数无效，只能靠大 `limit` 一次取全

---

## 9. 快速验收清单

装完后按顺序跑一遍，全绿即可交付。

### 9.1 Linux / macOS

```bash
CLI="$HOME/.dsh/skills/age-anime/scripts/agedl_cli.py"
PY=python3

# 1. 环境
$PY "$CLI" doctor
# 2. 跨平台逻辑 + POSIX 端到端（两套测试，共 78 项断言）
$PY "$CLI" selftest
# 3. 榜单
$PY "$CLI" hot --src 总排行
# 4. 搜索
$PY "$CLI" search "命运" --limit 5
# 5. 集数
$PY "$CLI" series "https://www.age001.com/play/12537-1-1.html"
# 6. 真实地址
$PY "$CLI" probe "https://www.age001.com/play/12537-1-1.html" -n 1
# 7. 详情
$PY "$CLI" detail 12537
# 8. 下载一集（真下，约 60~120 秒 / 300 MB）
$PY "$CLI" download "https://www.age001.com/play/12537-1-1.html" -n 2 -o "${TMPDIR:-/tmp}/agetest"
# 9. 校验成品
ffprobe -v error -show_entries format=duration,size \
        -of default=noprint_wrappers=1 \
        "${TMPDIR:-/tmp}/agetest/命运奇异赝品 第02集.mp4"
```

### 9.2 Windows（PowerShell）

```powershell
$CLI = "$env:USERPROFILE\.dsh\skills\age-anime\scripts\agedl_cli.py"
$PY  = "python"

& $PY $CLI doctor
& $PY $CLI selftest
& $PY $CLI hot --src 总排行
& $PY $CLI search "命运" --limit 5
& $PY $CLI series "https://www.age001.com/play/12537-1-1.html"
& $PY $CLI probe "https://www.age001.com/play/12537-1-1.html" -n 1
& $PY $CLI detail 12537
& $PY $CLI download "https://www.age001.com/play/12537-1-1.html" -n 2 -o "$env:TEMP\agetest"

ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 `
        "$env:TEMP\agetest\命运奇异赝品 第02集.mp4"
```

### 9.3 期望结果

- 前 8 步全部 `ok: true` / 退出码 0
- `selftest` 的 `summary` 是 `2/2 套测试通过`
- 第 9 步能读出 `duration=1425` 左右、`size` 约 3.1 亿字节（327,851,247 是本机实测值）
- 下载那一步的 stderr 里如果出现「检测到写权限被限制，改用临时目录里的 ffmpeg 副本重试」，
  说明自动逃逸机制生效了，**这是正常现象**，不是错误

---

## 10. 已知限制

| 限制 | 说明 |
|---|---|
| 只支持 age001.com | 站点改版会导致解析失效，需更新 `core.py`/`discover.py` 的正则 |
| 只做无损封装 | 不转码、不压码率、不切片。要转码请自己调 ffmpeg |
| 搜索上限 200 条 | 服务端 `limit` 硬限 |
| 最新入库每页 20 条 | 服务端 `limit` 硬限 |
| 榜单不返回年份/地区 | 榜单页没这些数据，需对每条调 `detail` 补全（有网络开销） |
| 无断点续传（单分片级） | 已下载的整集文件会跳过；但下到一半的整集不会接着下 |
| 无进度条回调给外部 | 进度只在 stderr 打文本日志 |
| Linux/macOS 未跑过完整在线下载 | 跨平台逻辑有 78 项断言覆盖（文件名规则、路径候选、执行位、一次真实封装），但首次上真机建议先跑 `probe` 确认网络与解析，见 §7.7 |
| 文件名大小写在 Linux 上敏感 | 已有 `第01集.MP4` 时再下 `第01集.mp4` 会生成两个文件；本工具扩展名固定小写，正常不会撞 |

---

## 附录 A：目录结构一览

```
<skills目录>\age-anime\
├── SKILL.md                7.3 KB   agent 读取的说明书（frontmatter + 路由 + 坑）
├── DEPLOY.md              31.9 KB   本文档（部署与使用手册）
└── scripts\
    ├── agedl_cli.py       22.6 KB   命令行入口，8 个子命令 + selftest
    ├── core.py            38.2 KB   播放页解析 / HLS / 分片下载 / 无损封装
    ├── discover.py        20.7 KB   榜单 / 搜索 / 详情
    ├── platform_compat.py  8.3 KB   跨平台差异（文件名、ffmpeg 路径、执行位）
    ├── test_platform.py    7.6 KB   52 项跨平台逻辑断言（不需要网络/ffmpeg）
    └── test_posix_sim.py   7.8 KB   26 项 POSIX 端到端断言（需要 ffmpeg）
```

合计约 **124 KB**（不含 ffmpeg）。若把 ffmpeg + ffprobe 一起打包，约 **+340 MB**。

`platform_compat.py` 是唯一的平台判断场所。要支持一个新平台，
只需要改这一个文件里的 `ffmpeg_candidate_dirs()` 与 `exe_names()`；
其它模块不写 `if sys.platform == ...`。

---

## 附录 B：一键安装脚本（Windows）

保存为 `install-age-anime.ps1`，和 `age-anime` 目录放在一起，右键「使用 PowerShell 运行」：

```powershell
# install-age-anime.ps1
$ErrorActionPreference = "Stop"
$dest = "C:\Users\$env:USERNAME\.dsh\skills"

Write-Host "[1/4] 检查 Python …" -ForegroundColor Cyan
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "没找到 python，请先安装 Python 3.9+ 并加入 PATH" }
Write-Host "      $py"

Write-Host "[2/4] 检查 requests …" -ForegroundColor Cyan
& $py -c "import requests" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      安装 requests …"
    & $py -m pip install requests
}

Write-Host "[3/4] 拷贝 skill …" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$src = Join-Path $PSScriptRoot "age-anime"
if (-not (Test-Path $src)) { throw "当前目录下没有 age-anime 文件夹" }
if (Test-Path (Join-Path $dest "age-anime")) {
    Remove-Item (Join-Path $dest "age-anime") -Recurse -Force
}
Copy-Item $src -Destination $dest -Recurse -Force
# 清掉源机器留下的字节码
$pyc = Join-Path $dest "age-anime\scripts\__pycache__"
if (Test-Path $pyc) { Remove-Item $pyc -Recurse -Force }

Write-Host "[4/4] 自检 …" -ForegroundColor Cyan
$cli = Join-Path $dest "age-anime\scripts\agedl_cli.py"
& $py $cli doctor

Write-Host ""
Write-Host "完成。skill 已装到 $dest\age-anime" -ForegroundColor Green
Write-Host "重启 DSH 后即可在对话里说「用 age-anime 看看本周排行」" -ForegroundColor Green
```

## 附录 B2：一键安装脚本（Linux / macOS）

保存为 `install-age-anime.sh`，放在 `age-anime` 目录的**上一级**，然后
`chmod +x install-age-anime.sh && ./install-age-anime.sh`。

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── 可调参数 ────────────────────────────────────────────────
SKILL_NAME="age-anime"
DEST="${DSH_HOME:-$HOME/.dsh}/skills"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${SKILL_NAME}"

say()  { printf '\033[36m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
die()  { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

# ── 1. 检查 Python ─────────────────────────────────────────
say "[1/5] 检查 Python"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || die "没找到 python3，请先安装 Python 3.9+"
VER="$($PY -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
case "$VER" in
  3.9|3.1[0-9]) : ;;
  *) die "Python $VER 太旧，需要 3.9+" ;;
esac
echo "      $($PY -V)  →  $(command -v "$PY")"

# ── 2. 检查 requests ───────────────────────────────────────
say "[2/5] 检查 requests"
if $PY -c 'import requests' 2>/dev/null; then
  echo "      已安装 $($PY -c 'import requests;print(requests.__version__)')"
else
  echo "      安装中 …"
  $PY -m pip install --quiet requests || die "requests 安装失败"
fi

# ── 3. 检查 ffmpeg ─────────────────────────────────────────
say "[3/5] 检查 ffmpeg"
if command -v ffmpeg >/dev/null 2>&1; then
  echo "      $(command -v ffmpeg)  →  $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
else
  warn "      未找到 ffmpeg。可以继续安装，但没有它只能下到 .raw（未封装）。"
  if   command -v apt    >/dev/null 2>&1; then warn "      安装：sudo apt install ffmpeg"
  elif command -v dnf    >/dev/null 2>&1; then warn "      安装：sudo dnf install ffmpeg"
  elif command -v pacman >/dev/null 2>&1; then warn "      安装：sudo pacman -S ffmpeg"
  elif command -v brew   >/dev/null 2>&1; then warn "      安装：brew install ffmpeg"
  fi
  warn "      或解压一个静态版到 \$HOME/ffmpeg/bin 并把该目录加进 PATH。"
fi

# ── 4. 复制 skill ─────────────────────────────────────────
say "[4/5] 安装到 $DEST/$SKILL_NAME"
[ -d "$SRC" ] || die "当前目录下没有 $SKILL_NAME 文件夹（脚本要和它同级）"
mkdir -p "$DEST"
rm -rf "$DEST/$SKILL_NAME"
cp -R "$SRC" "$DEST/$SKILL_NAME"
# 别把开发机的字节码带过去
find "$DEST/$SKILL_NAME" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST/$SKILL_NAME" -name '*.pyc' -delete 2>/dev/null || true
# 清掉 macOS 的隔离标记（有 xattr 才做）
if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$DEST/$SKILL_NAME" 2>/dev/null || true
fi
echo "      已复制 $(find "$DEST/$SKILL_NAME" -type f | wc -l | tr -d ' ') 个文件"

# ── 5. 自检 ───────────────────────────────────────────────
say "[5/5] 运行 doctor"
cd "$DEST/$SKILL_NAME/scripts"
$PY agedl_cli.py doctor || die "doctor 失败（看上面的 JSON 里哪一项是 false）"

echo
say "安装完成。"
echo "  给 agent 用：让它读 age-anime skill，或直接说「下载某番第几集」"
echo "  手动用：cd $DEST/$SKILL_NAME/scripts && $PY agedl_cli.py hot"
```

---

## 附录 C：卸载

```powershell
Remove-Item "C:\Users\$env:USERNAME\.dsh\skills\age-anime" -Recurse -Force
# 如果设过环境变量
[Environment]::SetEnvironmentVariable("AGEDL_FFMPEG", $null, "User")
```

下载的视频不会被删——它们在你的输出目录里。
