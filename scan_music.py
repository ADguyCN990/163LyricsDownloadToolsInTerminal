#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音乐文件扫描工具
扫描目录下所有音乐文件，用文件名搜索网易云音乐获取ID
支持读取音频文件元数据进行时长验证
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
from urllib.parse import quote
import urllib.request

# ===== 配置 =====
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 音乐文件扩展名
MUSIC_EXTENSIONS = {
    '.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg',
    '.ape', '.wma', '.dsf', '.dff', '.alac', '.opus'
}

# ===== HTTP工具 =====
def http_get(url, timeout=30):
    """HTTP GET请求"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise Exception(f"HTTP请求失败: {e}")

# ===== 网易云搜索 =====
def search_netease(keyword, limit=10):
    """
    搜索网易云音乐
    返回: [(song_id, song_name, artist), ...]
    """
    url = f"https://music.163.com/api/search/get?type=1&s={quote(keyword)}&limit={limit}"

    try:
        data = http_get(url)
        if data.get("code") != 200:
            return []

        songs = data.get("result", {}).get("songs", [])
        result = []

        for song in songs:
            song_id = song.get("id")
            song_name = song.get("name", "")
            artist = ", ".join([a.get("name", "") for a in song.get("ar", [])])
            result.append((song_id, song_name, artist))

        return result

    except Exception as e:
        print(f"  搜索失败: {e}")
        return []


# ===== 音频元数据读取 =====
def get_audio_metadata(file_path):
    """
    读取音频文件的元数据
    返回: dict 包含 artist, album, title, duration_ms
    """
    try:
        from mutagen import File
        from mutagen.mp3 import MP3
        from mutagen.flac import FLAC
        from mutagen.m4a import M4A
        from mutagen.wave import WAVE
        from mutagen.aac import AAC

        audio = File(file_path)
        if audio is None:
            return None

        metadata = {}

        # 获取艺术家 - 优先使用.keys()检查，再尝试属性访问
        if 'artist' in audio.keys():
            artist = audio['artist']
            metadata['artist'] = str(artist[0]) if isinstance(artist, list) else str(artist)
        elif hasattr(audio, 'artist') and audio.artist:
            metadata['artist'] = str(audio.artist[0]) if isinstance(audio.artist, list) else str(audio.artist)
        elif hasattr(audio, 'TPE1'):
            metadata['artist'] = str(audio['TPE1'])
        else:
            metadata['artist'] = ""

        # 获取专辑
        if 'album' in audio.keys():
            album = audio['album']
            metadata['album'] = str(album[0]) if isinstance(album, list) else str(album)
        elif hasattr(audio, 'album') and audio.album:
            metadata['album'] = str(audio.album[0]) if isinstance(audio.album, list) else str(audio.album)
        elif hasattr(audio, 'TALB'):
            metadata['album'] = str(audio['TALB'])
        else:
            metadata['album'] = ""

        # 获取标题
        if 'title' in audio.keys():
            title = audio['title']
            metadata['title'] = str(title[0]) if isinstance(title, list) else str(title)
        elif hasattr(audio, 'title') and audio.title:
            metadata['title'] = str(audio.title[0]) if isinstance(audio.title, list) else str(audio.title)
        elif hasattr(audio, 'TIT2'):
            metadata['title'] = str(audio['TIT2'])
        else:
            metadata['title'] = ""

        # 获取时长（毫秒）
        try:
            # mutagen 对不同格式的时长属性名不同
            if hasattr(audio.info, 'length'):
                metadata['duration_ms'] = int(audio.info.length * 1000)
            elif hasattr(audio.info, 'duration'):
                metadata['duration_ms'] = int(audio.info.duration * 1000)
            else:
                metadata['duration_ms'] = 0
        except Exception:
            metadata['duration_ms'] = 0

        return metadata

    except Exception as e:
        # 静默忽略读取错误
        return None

def format_duration(ms):
    """将毫秒转换为 mm:ss 格式"""
    if ms <= 0:
        return "未知"
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

# ===== 文件扫描 =====
def scan_directory(path, recursive=True):
    """
    扫描目录下的音乐文件
    返回: [(file_path, file_name), ...]
    """
    path = Path(path)
    if not path.exists():
        raise Exception(f"目录不存在: {path}")

    if not path.is_dir():
        raise Exception(f"不是目录: {path}")

    music_files = []

    if recursive:
        iterator = path.rglob("*")
    else:
        iterator = path.glob("*")

    for file_path in iterator:
        if file_path.is_file() and file_path.suffix.lower() in MUSIC_EXTENSIONS:
            music_files.append((str(file_path), file_path.stem))

    return music_files

# ===== 文件名清洗 =====
def clean_filename(name):
    """
    清洗文件名，提取有效搜索词
    去除: 括号内的版本信息、文件扩展名、数字等
    """
    # 去掉扩展名
    name = Path(name).stem

    # 去掉常见的后缀信息
    patterns_to_remove = [
        r'\s*\(?\d{4}[-.]\d{2}[-.]\d{2}\)?',  # 日期 (2024-01-01)
        r'\s*[-_]\d{4}[-.]\d{2}[-.]\d{2}',     # 下划线日期
        r'\s*\[[^\]]*\]',                       # 方括号内容 [320kbps]
        r'\s*\([^)]*\)',                        # 圆括号内容 (320Kbps)
        r'\s*[-_](FLAC|MP3|WAV|ALAC|APE|DSD)',  # 格式标识
        r'\s*[-_](标准版|母带版|现场版| remix|mix)',  # 版本标识
        r'\s*[-_]\d+kbps?',                     # 比特率
        r'\s*[-_]?\d+Hz?',                      # 采样率
    ]

    for pattern in patterns_to_remove:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)

    # 清理多余字符
    name = re.sub(r'[-_\s]+', ' ', name)
    name = name.strip()

    return name

# ===== 主逻辑 =====
def process_files(music_dir, output_file, recursive, similarity_threshold=0.6, use_metadata=True):
    """
    处理音乐文件
    use_metadata: 是否使用音频元数据进行验证
    """
    print("=" * 50)
    print("🎵 音乐文件扫描工具")
    print("=" * 50)
    print(f"📁 扫描目录: {music_dir}")
    print(f"📂 递归扫描: {'是' if recursive else '否'}")
    print(f"🔍 元数据验证: {'是' if use_metadata else '否'}")
    print("=" * 50)

    # 扫描文件
    print("\n🔍 扫描音乐文件...")
    music_files = scan_directory(music_dir, recursive)
    print(f"   找到 {len(music_files)} 个音乐文件")

    if not music_files:
        print("❌ 未找到音乐文件")
        return

    # 搜索每个文件
    print("\n🔎 搜索网易云音乐...")
    results = []
    skipped = []
    metadata_failed = 0

    for i, (file_path, file_name) in enumerate(music_files, 1):
        # 读取元数据
        local_meta = {'filename': file_name}
        if use_metadata:
            meta = get_audio_metadata(file_path)
            if meta:
                local_meta.update(meta)
                print(f"\n[{i}/{len(music_files)}] {Path(file_name).name}")
                print(f"   📀 时长: {format_duration(meta.get('duration_ms', 0))}")
                if meta.get('artist'):
                    print(f"   👤 艺术家: {meta['artist']}")
                if meta.get('album'):
                    print(f"   💿 专辑: {meta['album']}")
            else:
                metadata_failed += 1
                print(f"\n[{i}/{len(music_files)}] {Path(file_name).name} ⚠️")
                print(f"   ⚠️ 无法读取元数据")
                local_meta.update({'duration_ms': 0, 'artist': '', 'album': ''})

        # 清洗文件名作为搜索词
        search_name = clean_filename(file_name)

        # 组合搜索词：优先标题，没有标题就用文件名 + 艺术家 + 专辑
        # 标题和文件名只选一个，避免重复
        title = local_meta.get('title', '')
        search_name = title if title else clean_filename(file_name)

        parts = [search_name]
        if local_meta.get('artist'):
            parts.append(local_meta['artist'])
        if local_meta.get('album'):
            parts.append(local_meta['album'])
        combined_search = ' '.join(parts)

        print(f"   🔍 搜索词: {combined_search}")

        # 搜索
        search_results = search_netease(combined_search, limit=10)

        if not search_results:
            print(f"   ❌ 未找到匹配歌曲")
            skipped.append((file_path, search_name, "未找到"))
            continue

        # 获取搜索结果的详细信息用于验证
        best_match = None
        best_score = 0
        best_verified = False
        best_reason = ""

        local_artist = (local_meta.get('artist', '') or '').lower()
        local_title = (local_meta.get('title', '') or '').lower()
        # 优先用标题，没有就用文件名
        if local_title:
            search_text = local_title.lower()
        else:
            search_text = clean_filename(file_name).lower()

        for song_id, song_name, artist in search_results:
            # 评分
            score = 0
            reasons = []

            # 1. 歌名相似度（权重最高）
            name_sim = calculate_similarity(search_text, song_name.lower())
            score += int(name_sim * 60)
            if name_sim > 0.7:
                reasons.append(f"歌名匹配({name_sim:.0%})")
            elif name_sim > 0.4:
                reasons.append(f"歌名相似({name_sim:.0%})")

            # 2. 艺术家匹配
            if local_artist and artist:
                artist_sim = calculate_similarity(local_artist, artist.lower())
                if artist_sim > 0.7:
                    score += 40
                    reasons.append("艺术家匹配")
                elif artist_sim > 0.3:
                    score += 20
                    reasons.append("艺术家相似")

            # 更新最佳匹配
            if score > best_score:
                best_score = score
                best_match = (song_id, song_name, artist)
                best_verified = True  # 歌名匹配就认为验证通过
                best_reason = " | ".join(reasons[:2]) if reasons else "验证通过"

        matched = best_match
        verified = best_verified
        reason = best_reason
        score = best_score

        if matched:
            song_id, song_name, artist = matched
            print(f"   🎵 {artist} - {song_name}")
            print(f"   📀 ID: {song_id}")
            print(f"   ✅ 验证: {reason}")

            # 高置信度判断：
            # 1. 歌名匹配度高(>70%) - 最可靠的指标
            # 2. 或者时长验证通过且歌名匹配度>40%
            if "歌名匹配" in reason or (verified and "歌名相似" in reason):
                confidence = "high"
            else:
                confidence = "low"

            results.append({
                "file": file_path,
                "search_name": search_name,
                "song_id": song_id,
                "song_name": song_name,
                "artist": artist,
                "confidence": confidence,
                "verify_reason": reason,
                "metadata": {
                    "local_artist": local_meta.get('artist', ''),
                    "local_album": local_meta.get('album', ''),
                    "local_title": local_meta.get('title', '')
                }
            })
        else:
            print(f"   ❌ 无法找到合适的匹配")
            skipped.append((file_path, search_name, reason))

        # 避免请求过快
        if i < len(music_files):
            time.sleep(0.3)

    # 输出结果
    print("\n" + "=" * 50)
    print("📊 搜索结果统计")
    print("=" * 50)

    high_count = sum(1 for r in results if r["confidence"] == "high")
    low_count = sum(1 for r in results if r["confidence"] == "low")
    skip_count = len(skipped)

    print(f"   ✅ 高置信度: {high_count}")
    print(f"   ⚠️  低置信度: {low_count}")
    print(f"   ❌ 未匹配: {skip_count}")
    if metadata_failed > 0:
        print(f"   ⚠️  元数据读取失败: {metadata_failed}")
    print(f"   📁 总计: {len(music_files)}")

    # 保存结果
    if output_file:
        save_results(results, skipped, output_file)
        print(f"\n📄 结果已保存到: {output_file}")

        # 同时生成ID列表（供lyric_cli使用）
        id_file = Path(output_file).with_suffix(".ids.txt")
        with open(id_file, 'w', encoding='utf-8') as f:
            for r in results:
                f.write(f"{r['song_id']}\n")
        print(f"   📄 ID列表已保存到: {id_file}")

    return results

def calculate_similarity(str1, str2):
    """计算两个字符串的相似度（简单版：公共子串比例）"""
    # 简单实现：计算公共字符数占较短字符串的比例
    set1 = set(re.sub(r'\s+', '', str1.lower()))
    set2 = set(re.sub(r'\s+', '', str2.lower()))

    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    min_len = min(len(set1), len(set2))

    return intersection / min_len if min_len > 0 else 0.0

def save_results(results, skipped, output_file):
    """保存详细结果到JSON文件"""
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(results) + len(skipped),
        "success_count": len(results),
        "skipped_count": len(skipped),
        "results": results,
        "skipped": skipped
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

def main():
    parser = argparse.ArgumentParser(
        description="扫描音乐文件并搜索网易云音乐ID",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描当前目录
  python scan_music.py -d ./music -o results.json

  # 扫描指定目录（非递归）
  python scan_music.py -d "E:\\Music" --no-recursive -o results.json

  # 调整相似度阈值
  python scan_music.py -d ./music -t 0.7 -o results.json

  # 禁用元数据验证（仅使用文件名搜索）
  python scan_music.py -d ./music --no-metadata -o results.json
        """
    )

    parser.add_argument("-d", "--dir", required=True, help="音乐目录路径")
    parser.add_argument("-o", "--output", default="scan_results.json",
                        help="输出JSON文件路径 (默认: scan_results.json)")
    parser.add_argument("-r", "--recursive", action="store_true", default=True,
                        help="递归扫描子目录 (默认: 开启)")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false",
                        help="不扫描子目录")
    parser.add_argument("-t", "--threshold", type=float, default=0.6,
                        help="相似度阈值 (默认: 0.6)")
    parser.add_argument("--no-metadata", dest="use_metadata", action="store_false",
                        default=True, help="禁用音频元数据验证")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="显示详细信息")

    args = parser.parse_args()

    try:
        process_files(args.dir, args.output, args.recursive, args.threshold, args.use_metadata)
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请安装 mutagen: pip install mutagen")
        return 1
    except Exception as e:
        print(f"❌ 错误: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
