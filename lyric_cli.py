#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云/QQ音乐歌词下载工具 - CLI版本
支持单曲链接、批量输入，输出LRC文件到指定目录
"""

import sys
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
import re
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, unquote
import urllib.request
import urllib.error
import gzip

# 导入网易云weapi加密模块
from netease_crypto import weapi_encrypt

# ===== 配置 =====
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ===== 工具函数 =====
def http_get(url, headers=None, retry=3, retry_delay=2):
    """HTTP GET请求，带重试机制"""
    import time as time_module

    for attempt in range(retry):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))

                # 检查是否被限流
                if isinstance(data, dict) and data.get("code") in [405, 429, 503]:
                    error_msg = data.get("msg", data.get("message", "未知错误"))
                    if attempt < retry - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        print(f"     ⚠️  API限流 ({error_msg}), {wait_time}秒后重试...")
                        time_module.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"API限流: {error_msg}")

                return data

        except urllib.error.HTTPError as e:
            if e.code in [405, 429, 503]:
                if attempt < retry - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"     ⚠️  HTTP {e.code}, {wait_time}秒后重试...")
                    time_module.sleep(wait_time)
                    continue
                raise Exception(f"HTTP {e.code}: 请求被拒绝")
        except Exception as e:
            if attempt < retry - 1:
                wait_time = retry_delay * (2 ** attempt)
                time_module.sleep(wait_time)
                continue
            raise Exception(f"HTTP请求失败: {e}")

    raise Exception("请求失败")

def http_post(url, data, headers=None):
    """HTTP POST请求"""
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'))
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise Exception(f"HTTP请求失败: {e}")

def parse_input(input_str):
    """
    解析输入，返回 (类型, ID/关键词)
    类型: 'netease_song', 'netease_album', 'netease_playlist', 'qq_song', 'qq_album', 'qq_playlist'
    """
    input_str = input_str.strip()

    # 网易云音乐
    # 单曲: https://music.163.com/#/song?id=12345
    # 专辑: https://music.163.com/#/album?id=12345
    # 歌单: https://music.163.com/#/playlist?id=12345
    netease_patterns = [
        (r'music\.163\.com.*?song\?id=(\d+)', 'netease_song'),
        (r'music\.163\.com.*?album\?id=(\d+)', 'netease_album'),
        (r'music\.163\.com.*?playlist\?id=(\d+)', 'netease_playlist'),
        (r'^(\d{6,10})$', 'netease_song'),  # 纯数字ID (6-10位)
    ]

    # QQ音乐
    # 单曲: https://y.qq.com/n/ryg/songdetail/12345.html
    # 专辑: https://y.qq.com/n/ryg/album/12345.html
    # 歌单: https://y.qq.com/n/ryg/playlist/12345.html
    qq_patterns = [
        (r'y\.qq\.com.*?songdetail/(\w+)\.html', 'qq_song'),
        (r'y\.qq\.com.*?album/(\w+)\.html', 'qq_album'),
        (r'y\.qq\.com.*?playlist/(\w+)\.html', 'qq_playlist'),
    ]

    for pattern, type_name in netease_patterns:
        match = re.search(pattern, input_str)
        if match:
            return type_name, match.group(1)

    for pattern, type_name in qq_patterns:
        match = re.search(pattern, input_str)
        if match:
            return type_name, match.group(1)

    # 默认当作网易云单曲关键词搜索
    return 'netease_search', input_str

# ===== 网易云音乐API =====
class NetEaseMusic:
    API_URL = "https://music.163.com/api"
    WEAPI_URL = "https://music.163.com/weapi"

    @staticmethod
    def get_song_lyric(song_id):
        """获取歌词 - 使用weapi加密"""
        url = f"{NetEaseMusic.WEAPI_URL}/song/lyric"

        # weapi参数
        data = {
            "id": song_id,
            "lv": -1,       # 原文歌词
            "tv": -1,       # 翻译歌词
            "kv": -1,
            "rv": -1,
            "yv": -1,
            "ytv": -1,
            "yrv": -1
        }

        try:
            # 使用weapi加密
            encrypted = weapi_encrypt(data)

            # POST请求
            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(encrypted).encode('utf-8'),
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://music.163.com/",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                # 处理 gzip 压缩响应
                if resp.info().get('Content-Encoding') == 'gzip':
                    result = json.loads(gzip.decompress(resp.read()).decode('utf-8'))
                else:
                    result = json.loads(resp.read().decode('utf-8'))

                if result.get("code") != 200:
                    raise Exception(f"获取歌词失败: {result}")

                lrc = result.get("lrc", {}).get("lyric", "")
                tlyric = result.get("tlyric", {}).get("lyric", "")

                return lrc, tlyric

        except Exception as e:
            raise Exception(f"获取歌词失败: {e}")

    @staticmethod
    def get_song_detail(song_id):
        """获取歌曲详情 - 使用weapi加密"""
        url = f"{NetEaseMusic.WEAPI_URL}/song/detail"

        # weapi参数
        data = {
            "ids": [song_id]
        }

        try:
            # 使用weapi加密
            encrypted = weapi_encrypt(data)

            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(encrypted).encode('utf-8'),
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://music.163.com/",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                # 处理 gzip 压缩响应
                if resp.info().get('Content-Encoding') == 'gzip':
                    result = json.loads(gzip.decompress(resp.read()).decode('utf-8'))
                else:
                    result = json.loads(resp.read().decode('utf-8'))

                if result.get("code") != 200:
                    raise Exception(f"获取详情失败: {result}")

                songs = result.get("songs", [])
                if not songs:
                    raise Exception("歌曲不存在")

                song = songs[0]
                # weapi 使用 artists 数组，api 使用 ar 字段
                artists = song.get("artists") or song.get("ar", [])
                artist_names = ", ".join([a.get("name", "") for a in artists])

                # weapi 使用 album 对象，api 使用 al 字段
                album_info = song.get("album") or song.get("al", {})
                album_name = album_info.get("name", "") if isinstance(album_info, dict) else str(album_info)

                return {
                    "name": song.get("name", ""),
                    "artist": artist_names,
                    "album": album_name,
                }

        except Exception as e:
            raise Exception(f"获取歌曲详情失败: {e}")

    @staticmethod
    def get_album_songs(album_id):
        """获取专辑下所有歌曲 - 使用weapi加密"""
        url = f"{NetEaseMusic.WEAPI_URL}/album/detail"

        # weapi参数
        data = {"id": album_id}

        try:
            # 使用weapi加密
            encrypted = weapi_encrypt(data)

            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(encrypted).encode('utf-8'),
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://music.163.com/",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                # 处理 gzip 压缩响应
                if resp.info().get('Content-Encoding') == 'gzip':
                    result = json.loads(gzip.decompress(resp.read()).decode('utf-8'))
                else:
                    result = json.loads(resp.read().decode('utf-8'))

                if result.get("code") != 200:
                    raise Exception(f"获取专辑失败: {result}")

                songs = result.get("songs", [])
                return [song.get("id") for song in songs]

        except Exception as e:
            raise Exception(f"获取专辑失败: {e}")

    @staticmethod
    def get_playlist_songs(playlist_id):
        """获取歌单下所有歌曲 - 使用weapi加密"""
        url = f"{NetEaseMusic.WEAPI_URL}/playlist/detail"

        # weapi参数
        data = {"id": playlist_id, "limit": 1000, "offset": 0}

        try:
            # 使用weapi加密
            encrypted = weapi_encrypt(data)

            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(encrypted).encode('utf-8'),
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://music.163.com/",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                # 处理 gzip 压缩响应
                if resp.info().get('Content-Encoding') == 'gzip':
                    result = json.loads(gzip.decompress(resp.read()).decode('utf-8'))
                else:
                    result = json.loads(resp.read().decode('utf-8'))

                if result.get("code") != 200:
                    raise Exception(f"获取歌单失败: {result}")

                tracks = result.get("playlist", {}).get("tracks", [])
                return [track.get("id") for track in tracks]

        except Exception as e:
            raise Exception(f"获取歌单失败: {e}")

    @staticmethod
    def search_song(keyword):
        """搜索歌曲 - 使用weapi加密"""
        url = f"{NetEaseMusic.WEAPI_URL}/search/get"

        # weapi参数
        data = {
            "s": keyword,
            "type": 1,
            "limit": 10,
            "offset": 0
        }

        try:
            # 使用weapi加密
            encrypted = weapi_encrypt(data)

            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(encrypted).encode('utf-8'),
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://music.163.com/",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                # 处理 gzip 压缩响应
                if resp.info().get('Content-Encoding') == 'gzip':
                    result = json.loads(gzip.decompress(resp.read()).decode('utf-8'))
                else:
                    result = json.loads(resp.read().decode('utf-8'))

                result_data = result.get("result", {})
                songs = result_data.get("songs", [])

                if not songs:
                    raise Exception(f"未找到歌曲: {keyword}")

                return songs[0].get("id")

        except Exception as e:
            raise Exception(f"搜索失败: {e}")

# ===== QQ音乐API =====
class QQMusic:
    BASE_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"

    # 缺失的API实现 - 简化版本
    @staticmethod
    def get_song_lyric(song_id):
        """获取歌词 - QQ音乐需要更复杂的实现"""
        # QQ音乐的API实现较为复杂，这里先抛出提示
        raise Exception("QQ音乐API暂未实现，请使用网易云音乐")

    @staticmethod
    def get_song_detail(song_id):
        """获取歌曲详情"""
        raise Exception("QQ音乐API暂未实现")

    @staticmethod
    def search_song(keyword):
        """搜索歌曲"""
        raise Exception("QQ音乐API暂未实现")

# ===== 歌词处理 =====
def merge_lyrics(lrc, tlyric=None, merge_type="both"):
    """
    合并歌词
    merge_type: 'original', 'translated', 'both'
    """
    lines = lrc.strip().split('\n') if lrc else []
    result = []

    if merge_type == "original" or not tlyric:
        return lrc

    # 翻译歌词解析
    t_lines = {}
    if tlyric:
        for line in tlyric.strip().split('\n'):
            match = re.match(r'\[(\d+):(\d+\.?\d*)\](.*)', line)
            if match:
                ms = int(match.group(1)) * 60000 + int(float(match.group(2)) * 1000)
                t_lines[ms] = match.group(3).strip()

    # 合并
    for line in lines:
        match = re.match(r'\[(\d+):(\d+\.?\d*)\](.*)', line)
        if match:
            ms = int(match.group(1)) * 60000 + int(float(match.group(2)) * 1000)
            time_str = f"[{match.group(1)}:{match.group(2).rstrip('0').rstrip('.')}]"
            content = match.group(3).strip()

            if ms in t_lines and t_lines[ms]:
                result.append(f"{time_str}{content}")
                result.append(f"{time_str}♪ {t_lines[ms]}")
            else:
                result.append(line)

    return '\n'.join(result)

def format_time(ms):
    """毫秒转换为 [mm:ss.xx] 格式"""
    total_seconds = ms / 1000
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"[{minutes:02d}:{seconds:05.2f}]"

def parse_lrc_time(line):
    """解析LRC时间戳"""
    match = re.match(r'\[(\d+):(\d+\.?\d*)\]', line)
    if match:
        ms = int(match.group(1)) * 60000 + int(float(match.group(2)) * 1000)
        return ms
    return None

def sort_lrc(lrc_content):
    """按时间排序歌词（保留相同时间戳的行，用于双语歌词）"""
    lines = lrc_content.strip().split('\n')
    timed_lines = []
    other_lines = []

    for line in lines:
        time_ms = parse_lrc_time(line)
        if time_ms is not None:
            timed_lines.append((time_ms, line))
        else:
            other_lines.append(line)

    # 按时间排序，相同时间戳的行保持顺序
    timed_lines.sort(key=lambda x: (x[0], x[1]))

    # 不再去除重复时间戳的行，保留双语歌词
    unique_lines = [line for _, line in timed_lines]

    return '\n'.join(other_lines + unique_lines)

# ===== 文件保存 =====
def save_lrc(filepath, content, song_info=None):
    """保存LRC文件"""
    # 添加元数据注释
    header = ""
    if song_info:
        header = f"[ti:{song_info.get('name', '')}]\n"
        header += f"[ar:{song_info.get('artist', '')}]\n"
        header += f"[al:{song_info.get('album', '')}]\n"
        header += f"[by:163MusicLyrics-CLI]\n"
        header += f"[offset:0]\n"

    content = sort_lrc(content)
    final_content = header + content

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(final_content)

    return True

# ===== 主逻辑 =====
def download_single(input_str, output_dir, merge_type="both"):
    """下载单个歌曲的歌词"""
    input_type, param = parse_input(input_str)

    print(f"  📀 处理: {input_str}")

    if input_type == 'netease_search':
        print(f"     🔍 搜索关键词: {param}")
        song_id = NetEaseMusic.search_song(param)
        input_type = 'netease_song'
        param = str(song_id)

    try:
        if input_type == 'netease_song':
            song_id = int(param)
            lrc, tlyric = NetEaseMusic.get_song_lyric(song_id)
            if not lrc:
                print(f"     ⚠️  无歌词")
                return False

            song_info = NetEaseMusic.get_song_detail(song_id)
            merged = merge_lyrics(lrc, tlyric, merge_type)

            # 生成文件名：<歌曲名> - <艺术家名>.lrc
            name = song_info.get('name', '').strip()
            artist = song_info.get('artist', '').strip()
            if artist:
                filename = f"{name} - {artist}.lrc"
            else:
                filename = f"{name}.lrc"
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            filepath = Path(output_dir) / filename

            save_lrc(str(filepath), merged, song_info)
            print(f"     ✅ 已保存: {filepath.name}")
            return True

        elif input_type == 'netease_album':
            song_ids = NetEaseMusic.get_album_songs(param)
            print(f"     📀 专辑共 {len(song_ids)} 首歌曲")
            count = 0
            for song_id in song_ids:
                try:
                    download_single(str(song_id), output_dir, merge_type)
                    count += 1
                    time.sleep(0.3)
                except Exception as e:
                    print(f"     ❌ 失败: {e}")
            print(f"     ✅ 完成 {count}/{len(song_ids)} 首")
            return count > 0

        elif input_type == 'netease_playlist':
            song_ids = NetEaseMusic.get_playlist_songs(param)
            print(f"     📀 歌单共 {len(song_ids)} 首歌曲")
            count = 0
            for song_id in song_ids:
                try:
                    download_single(str(song_id), output_dir, merge_type)
                    count += 1
                    time.sleep(0.3)
                except Exception as e:
                    print(f"     ❌ 失败: {e}")
            print(f"     ✅ 完成 {count}/{len(song_ids)} 首")
            return count > 0

        elif input_type.startswith('qq_'):
            print(f"     ⚠️ QQ音乐暂未支持")
            return False

        else:
            print(f"     ❌ 未知类型: {input_type}")
            return False

    except Exception as e:
        print(f"     ❌ 错误: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="网易云/QQ音乐歌词下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 下载单个歌曲
  python lyric_cli.py "https://music.163.com/#/song?id=12345" -o ./lyrics

  # 批量下载（从文件）
  python lyric_cli.py -f urls.txt -o ./lyrics

  # 下载专辑
  python lyric_cli.py "https://music.163.com/#/album?id=12345" -o ./lyrics

  # 下载歌单
  python lyric_cli.py "https://music.163.com/#/playlist?id=12345" -o ./lyrics

支持的音乐平台:
  - 网易云音乐 (music.163.com)
  - QQ音乐 (y.qq.com) - 暂未实现
        """
    )

    parser.add_argument("inputs", nargs="*", help="歌曲链接或ID（可多个）")
    parser.add_argument("-f", "--file", help="批量输入文件（每行一个链接）")
    parser.add_argument("-o", "--output", default="./lyrics", help="输出目录 (默认: ./lyrics)")
    parser.add_argument("-m", "--merge", choices=["original", "translated", "both"],
                        default="both", help="歌词合并模式 (默认: both)")
    parser.add_argument("-d", "--delay", type=float, default=1.0, help="请求间隔秒数 (默认: 1.0)")

    args = parser.parse_args()

    # 收集所有输入
    all_inputs = []

    if args.file:
        if os.path.exists(args.file):
            with open(args.file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        all_inputs.append(line)
        else:
            print(f"❌ 文件不存在: {args.file}")
            return 1

    all_inputs.extend(args.inputs)

    if not all_inputs:
        parser.print_help()
        return 0

    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("🎵 歌词下载工具")
    print("=" * 50)
    print(f"📁 输出目录: {output_dir}")
    print(f"📝 合并模式: {args.merge}")
    print(f"🔗 共 {len(all_inputs)} 个任务")
    print("=" * 50)

    success = 0
    failed = 0

    for i, input_str in enumerate(all_inputs, 1):
        print(f"\n[{i}/{len(all_inputs)}]", end="")
        try:
            if download_single(input_str, str(output_dir), args.merge):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ❌ 处理失败: {e}")
            failed += 1

        if i < len(all_inputs):
            time.sleep(args.delay)

    print("\n" + "=" * 50)
    print(f"✅ 完成! 成功: {success}, 失败: {failed}")
    print(f"📁 文件保存在: {output_dir.absolute()}")
    print("=" * 50)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
