#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 FLAC 文件的 artist 和 albumartist metadata 是否一致
用法: python check_flac_artist.py [音乐目录路径]
"""

import os
import sys
import json
from mutagen.flac import FLAC


def check_flac_files(root_dir):
    """遍历目录找出 artist/albumartist 不一致的 FLAC 文件"""
    mismatched = []

    for root, dirs, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith('.flac'):
                path = os.path.join(root, f)
                try:
                    audio = FLAC(path)
                    artist = audio.get('artist', [None])[0]
                    albumartist = audio.get('albumartist', [None])[0]

                    if artist is None:
                        artist = ''
                    if albumartist is None:
                        albumartist = ''

                    if artist.strip().lower() != albumartist.strip().lower():
                        rel_path = os.path.relpath(path, root_dir)
                        mismatched.append({
                            'file': rel_path,
                            'artist': artist,
                            'albumartist': albumartist
                        })
                except Exception as e:
                    print(f"Error reading {path}: {e}", file=sys.stderr)

    return mismatched


def main():
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = os.getcwd()

    print(f"扫描目录: {root_dir}")
    mismatched = check_flac_files(root_dir)

    if mismatched:
        print(f"\n找到 {len(mismatched)} 个 artist/albumartist 不一致的 FLAC 文件:\n")
        for item in mismatched:
            print(f"文件: {item['file']}")
            print(f"  artist:       '{item['artist']}'")
            print(f"  albumartist:  '{item['albumartist']}'")
            print()

        # 保存到 JSON 文件
        output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'mismatched_artist.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(mismatched, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {output_file}")
    else:
        print("没有找到 artist/albumartist 不一致的文件")


if __name__ == '__main__':
    main()
