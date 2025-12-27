#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将LRC歌词嵌入音乐文件元信息
扫描音乐目录和歌词目录，自动匹配并写入歌词元数据
"""

import sys
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
import re
import argparse
from pathlib import Path
from difflib import SequenceMatcher

# ===== 配置 =====
MUSIC_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.ape', '.wma', '.dsf', '.dff', '.alac', '.opus'}


# ===== 工具函数 =====
def parse_lrc_metadata(lrc_content):
    """解析LRC文件，提取元信息"""
    metadata = {}
    lyrics = []

    for line in lrc_content.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        # 解析元信息标签
        if line.startswith('[ti:'):
            match = re.match(r'\[ti:(.+)\]', line)
            if match:
                metadata['title'] = match.group(1).strip()
        elif line.startswith('[ar:'):
            match = re.match(r'\[ar:(.+)\]', line)
            if match:
                metadata['artist'] = match.group(1).strip()
        elif line.startswith('[al:'):
            match = re.match(r'\[al:(.+)\]', line)
            if match:
                metadata['album'] = match.group(1).strip()
        elif line.startswith('[by:'):
            match = re.match(r'\[by:(.+)\]', line)
            if match:
                metadata['by'] = match.group(1).strip()
        elif re.match(r'\[\d+:\d+', line):
            # 歌词行
            lyrics.append(line)

    metadata['lyrics'] = '\n'.join(lyrics)
    return metadata


def get_audio_metadata(file_path):
    """读取音频文件的元数据"""
    try:
        from mutagen import File

        audio = File(file_path)
        if audio is None:
            return None

        metadata = {}

        # 获取艺术家
        if 'artist' in audio.keys():
            artist = audio['artist']
            metadata['artist'] = str(artist[0]) if isinstance(artist, list) else str(artist)
        elif hasattr(audio, 'artist') and audio.artist:
            metadata['artist'] = str(audio.artist[0]) if isinstance(audio.artist, list) else str(audio.artist)
        elif hasattr(audio, 'TPE1'):
            metadata['artist'] = str(audio['TPE1'])
        else:
            metadata['artist'] = ""

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

        return metadata

    except Exception as e:
        return None


def calculate_similarity(str1, str2):
    """计算两个字符串的相似度"""
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def match_song_to_lrc(song_meta, lrc_files, threshold=0.6, filename=""):
    """
    匹配歌曲到LRC文件
    返回: (lrc_path, lrc_metadata, similarity) 或 (None, None, 0)
    """
    if not song_meta:
        song_meta = {'title': '', 'artist': '', 'album': ''}

    best_match = None
    best_score = 0
    best_lrc_meta = None

    song_title = (song_meta.get('title', '') or '').lower()
    song_artist = (song_meta.get('artist', '') or '').lower()
    filename_clean = Path(filename).stem.lower() if filename else ""

    for lrc_path in lrc_files:
        try:
            with open(lrc_path, 'r', encoding='utf-8') as f:
                content = f.read()

            lrc_meta = parse_lrc_metadata(content)

            # 跳过没有歌词内容的文件
            if not lrc_meta.get('lyrics', '').strip():
                continue

            lrc_title = (lrc_meta.get('title', '') or '').lower()
            lrc_artist = (lrc_meta.get('artist', '') or '').lower()

            # 计算相似度
            score = 0
            reasons = []

            # 标题匹配 (权重更高)
            if song_title and lrc_title:
                title_sim = calculate_similarity(song_title, lrc_title)
                score += title_sim * 70
                if title_sim > 0.8:
                    reasons.append(f"标题高度匹配({title_sim:.0%})")
                elif title_sim > 0.5:
                    reasons.append(f"标题相似({title_sim:.0%})")
            elif filename_clean and lrc_title:
                # 使用文件名匹配
                title_sim = calculate_similarity(filename_clean, lrc_title)
                score += title_sim * 50
                if title_sim > 0.8:
                    reasons.append(f"文件名匹配({title_sim:.0%})")
                elif title_sim > 0.5:
                    reasons.append(f"文件名相似({title_sim:.0%})")

            # 艺术家匹配
            if song_artist and lrc_artist:
                artist_sim = calculate_similarity(song_artist, lrc_artist)
                if artist_sim > 0.7:
                    score += 30
                    reasons.append("艺术家匹配")
                elif artist_sim > 0.4:
                    score += 15
                    reasons.append("艺术家相似")

            if score > best_score:
                best_score = score
                best_match = lrc_path
                best_lrc_meta = lrc_meta

        except Exception:
            continue

    if best_match and best_score >= threshold * 100:
        return best_match, best_lrc_meta, best_score / 100

    return None, None, 0


def embed_lyrics_to_audio(audio_path, lyrics_content):
    """
    将歌词嵌入音频文件元数据
    返回: (success, message)
    """
    try:
        from mutagen import File
        from mutagen.id3 import ID3, TXXX
        from mutagen.flac import FLAC
        from mutagen.mp3 import MP3
        from mutagen.m4a import M4A

        audio = File(audio_path)
        if audio is None:
            return False, "无法读取音频文件"

        lyrics_content = lyrics_content.strip()

        # 根据文件类型使用不同的方式写入歌词
        if isinstance(audio, MP3):
            # MP3 使用 ID3 标签
            if audio.tags is None:
                from mutagen.id3 import ID3
                audio.add_tags(ID3(audio.filename))

            # 清除旧的USLT标签
            if 'USLT:eng' in audio.tags:
                del audio.tags['USLT:eng']

            # 添加新的歌词标签
            audio.tags.add(TXXX(
                encoding=3,
                desc='LYRICS',
                text=lyrics_content
            ))

        elif isinstance(audio, FLAC):
            # FLAC 使用 Vorbis 注释
            if 'LYRICS' in audio.tags:
                del audio.tags['LYRICS']
            audio.tags['LYRICS'] = lyrics_content

        elif isinstance(audio, M4A):
            # M4A 使用 ©ly 标签
            if '\u00a9lyr' in audio.tags:
                del audio.tags['\u00a9lyr']
            audio.tags['\u00a9lyr'] = lyrics_content

        else:
            # 其他格式尝试使用 TXXX
            if 'LYRICS' in audio.tags:
                del audio.tags['LYRICS']
            audio.tags['LYRICS'] = lyrics_content

        audio.save()
        return True, "歌词已写入"

    except Exception as e:
        return False, f"写入失败: {e}"


def scan_directory(path, recursive=True):
    """扫描目录下的音乐文件"""
    path = Path(path)
    if not path.exists() or not path.is_dir():
        return []

    music_files = []
    iterator = path.rglob("*") if recursive else path.glob("*")

    for file_path in iterator:
        if file_path.is_file() and file_path.suffix.lower() in MUSIC_EXTENSIONS:
            music_files.append(str(file_path))

    return music_files


def scan_lrc_files(path):
    """扫描目录下的LRC文件"""
    path = Path(path)
    if not path.exists() or not path.is_dir():
        return []

    lrc_files = []
    for file_path in path.rglob("*.lrc"):
        lrc_files.append(str(file_path))

    return lrc_files


def main():
    parser = argparse.ArgumentParser(
        description="将LRC歌词嵌入音乐文件元信息",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法
  python embed_lyrics.py -m "E:\\音乐" -l "E:\\音乐\\lyrics"

  # 设置匹配阈值
  python embed_lyrics.py -m "E:\\音乐" -l "E:\\音乐\\lyrics" -t 0.7

  # 试运行模式（预览匹配结果）
  python embed_lyrics.py -m "E:\\音乐" -l "E:\\音乐\\lyrics" -n

  # 不扫描子目录
  python embed_lyrics.py -m "E:\\音乐" -l "E:\\音乐\\lyrics" --no-recursive
        """
    )

    parser.add_argument("-m", "--music", required=True, help="音乐目录路径")
    parser.add_argument("-l", "--lyrics", required=True, help="歌词目录路径")
    parser.add_argument("-t", "--threshold", type=float, default=0.6,
                        help="匹配阈值 0-1 (默认: 0.6)")
    parser.add_argument("-r", "--recursive", action="store_true", default=True,
                        help="递归扫描子目录 (默认: 开启)")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false",
                        help="不扫描子目录")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="试运行模式（不实际写入）")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="显示详细信息")

    args = parser.parse_args()

    # 验证目录
    music_dir = Path(args.music)
    lyrics_dir = Path(args.lyrics)

    if not music_dir.exists():
        print(f"❌ 音乐目录不存在: {music_dir}")
        return 1

    if not lyrics_dir.exists():
        print(f"❌ 歌词目录不存在: {lyrics_dir}")
        return 1

    # 扫描文件
    print("=" * 50)
    print("🎵 歌词嵌入工具")
    print("=" * 50)
    print(f"📁 音乐目录: {music_dir}")
    print(f"📝 歌词目录: {lyrics_dir}")
    print(f"🔍 递归扫描: {'是' if args.recursive else '否'}")
    print(f"🎯 匹配阈值: {args.threshold}")
    print(f"🔧 试运行: {'是' if args.dry_run else '否'}")
    print("=" * 50)

    print("\n🔍 扫描音乐文件...")
    music_files = scan_directory(args.music, args.recursive)
    print(f"   找到 {len(music_files)} 个音乐文件")

    if not music_files:
        print("❌ 未找到音乐文件")
        return 1

    print("\n📝 扫描LRC文件...")
    lrc_files = scan_lrc_files(args.lyrics)
    print(f"   找到 {len(lrc_files)} 个LRC文件")

    if not lrc_files:
        print("❌ 未找到LRC文件")
        return 1

    # 处理每个音乐文件
    print("\n🔎 匹配并嵌入歌词...")
    matched = 0
    skipped = 0
    failed = 0
    already_has = 0

    for i, audio_path in enumerate(music_files, 1):
        audio_path = Path(audio_path)
        print(f"\n[{i}/{len(music_files)}] {audio_path.name}")

        # 读取音频元数据
        song_meta = get_audio_metadata(str(audio_path))
        if song_meta:
            if song_meta.get('title'):
                print(f"   🎵 标题: {song_meta['title']}")
            if song_meta.get('artist'):
                print(f"   👤 艺术家: {song_meta['artist']}")
        else:
            print(f"   ⚠️ 无法读取元数据")
            song_meta = {'title': '', 'artist': '', 'album': ''}

        # 匹配歌词（传入文件名作为备选）
        lrc_path, lrc_meta, similarity = match_song_to_lrc(song_meta, lrc_files, args.threshold, str(audio_path))

        if lrc_path:
            lrc_path = Path(lrc_path)
            print(f"   📄 匹配歌词: {lrc_path.name}")
            print(f"   🎯 相似度: {similarity:.0%}")

            if lrc_meta.get('title'):
                print(f"   🎵 歌词标题: {lrc_meta['title']}")
            if lrc_meta.get('artist'):
                print(f"   👤 歌词艺术家: {lrc_meta['artist']}")

            if args.dry_run:
                print(f"   ℹ️  [试运行] 将嵌入歌词")
                matched += 1
                continue

            # 嵌入歌词
            lyrics_content = lrc_meta.get('lyrics', '')
            if lyrics_content:
                success, msg = embed_lyrics_to_audio(str(audio_path), lyrics_content)
                if success:
                    print(f"   ✅ {msg}")
                    matched += 1
                else:
                    print(f"   ❌ {msg}")
                    failed += 1
            else:
                print(f"   ⚠️ 歌词文件为空")
                skipped += 1
        else:
            print(f"   ❌ 未找到匹配的歌词")
            skipped += 1

    # 输出结果
    print("\n" + "=" * 50)
    print("📊 处理结果统计")
    print("=" * 50)
    print(f"   ✅ 成功嵌入: {matched}")
    print(f"   ❌ 嵌入失败: {failed}")
    print(f"   ⚠️  跳过: {skipped}")
    print(f"   📁 总计: {len(music_files)}")
    print("=" * 50)

    if args.dry_run:
        print("ℹ️  以上是试运行结果，未实际写入文件")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
