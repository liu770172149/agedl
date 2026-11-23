# -*- coding: utf-8 -*-
"""更新部署版说明书 + 重新打便携包。"""
import io
import os
import shutil
import subprocess
import sys
import time
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

APP = r"D:\AGE下载器"
README = os.path.join(APP, "使用说明.txt")
ZIP = r"D:\deepseekproject\AGE下载器_v1.1_便携版.zip"

TEXT = """AGE动漫 视频下载器  v1.1
================================================================
便携版 · 解压即用 · 无需安装 Python / ffmpeg

【重要】请勿把本程序放在 D:\\deepseekproject 目录下
  本机对该目录内的可执行文件有写入限制：程序只能往该目录里写文件，
  往其它盘/目录（如 D:\\迅雷下载、C:\\Users\\...）写会被系统拒绝，
  表现为「封装失败，保留 .raw」或 PermissionError。
  解压到 D:\\AGE下载器、D:\\软件\\AGE下载器 等任意其它位置即可正常。


一、图形界面用法
----------------------------------------------------------------
1. 粘贴播放页地址。形如：
     https://age001.com/play/12537-1-1.html
   （播放页、番剧详情页都行，程序会自动跳转）
2. 点「解析」。程序会读出剧名、总集数、每条线路各有多少集。
3. 在表格里勾选要下载的集数。可用：
     - 点第一列切换单集 ☑ / ☐
     - 「全选」「全不选」「反选」
     - 「第 N 集 到 第 M 集」批量勾选
     - 空格键批量切换选中行
   线路下拉框可切换「爱看」「魔都」等不同源（集数可能不同）。
4. 选输出目录、格式（MP4 / MKV）、并发数，点「开始下载」。
5. 进度条分别显示总进度与当前集进度，日志区实时输出每一步。


二、命令行用法（适合批量/脚本）
----------------------------------------------------------------
  AGE下载器.exe --cli <播放页地址> [选项]

  -n, --episodes    集数，默认 1。支持 1 / 1-13 / 1,3,5 / 1-5,8
  -o, --out         输出目录，默认 用户\\Downloads\\AGE动漫
  -f, --fmt         输出格式：mp4（默认）或 mkv
  -w, --workers     分片并发数，默认 16。网络不稳就调小
  --keep-segments   保留下载的分片缓存（可续传）
  --keep-ads        不剔除片源里的广告片段
  --selftest        只做自检：解析页面 + 找 ffmpeg，不下载

  例：
    AGE下载器.exe --cli https://age001.com/play/12537-1-1.html -n 1-13 -f mp4 -w 24 -o "D:\\动画"


三、输出说明
----------------------------------------------------------------
- MP4 / MKV 都是「无损封装」（-c copy），不重新编码，画质与源完全一致
- 下载过程会产生 .raw 中间文件，封装成功后自动删除
- 片源自带广告会被自动识别剔除（按 CDN 来源判定，正片跨分段也保留）
- 如果只看到 .raw 没有 MP4，说明封装被拦：
    1) 先确认程序不在 D:\\deepseekproject 下
    2) 或直接用同目录的 convert_raw.py 批量补转（见下）


四、常见问题
----------------------------------------------------------------
Q: 双击没反应 / 报错找不到 _internal
A: 本程序是 onedir 形式，必须整个文件夹一起用，不能只拷 exe。

Q: 360 报毒
A: PyInstaller 打包的程序常被误报。加信任即可，源码就在旁边可自行审查。

Q: 下载速度慢
A: 调大并发（最大 64）；若频繁失败则调小。片源单线程带宽有限。

Q: 为什么没有 TS 选项
A: 本机有透明加密驱动会接管 .ts 文件写入，产物会变成无法播放的密文容器。
   因此统一用 .raw 做中间文件，最终输出 MP4 或 MKV。

Q: 想批量把已有的 .raw 转成 MP4
A: 用配套脚本（需 Python）：
     python convert_raw.py "D:\\迅雷下载\\video"
   会自动找目录下所有 .raw 转 MP4，成功后删原件（加 --keep 保留）。


五、目录结构
----------------------------------------------------------------
  AGE下载器.exe          主程序
  使用说明.txt           本文件
  _internal\\             运行库（必需，勿删勿移）
    ffmpeg\\ffmpeg.exe    内置转封装工具
    ffmpeg\\ffprobe.exe   内置媒体信息工具
"""

with open(README, "w", encoding="utf-8-sig", newline="\r\n") as f:
    f.write(TEXT)
print(f"说明书已写入 {README}  {os.path.getsize(README):,} 字节")

# 校验体积
total = 0
nfile = 0
for root, _d, files in os.walk(APP):
    for f in files:
        total += os.path.getsize(os.path.join(root, f))
        nfile += 1
print(f"程序目录: {nfile} 个文件, {total / 1048576:.1f} MB")

# 重新打 zip
if os.path.isfile(ZIP):
    os.remove(ZIP)
print(f"打包 -> {ZIP} …")
t0 = time.time()
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for root, _d, files in os.walk(APP):
        for f in files:
            fp = os.path.join(root, f)
            arc = os.path.join("AGE下载器", os.path.relpath(fp, APP))
            z.write(fp, arc)
print(f"完成 {time.time() - t0:.1f}s, {os.path.getsize(ZIP) / 1048576:.1f} MB")

with zipfile.ZipFile(ZIP) as z:
    names = z.namelist()
print(f"包内 {len(names)} 个条目，示例：")
for n in names[:6]:
    print("  ", n)
