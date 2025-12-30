#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLAC 元数据检查与修复工具
功能：
1. 检查 artist/albumartist 是否一致
2. 记忆功能：记录处理状态
3. 交互式修复：选择覆盖方向或自定义
"""

import os
import sys
import json
from mutagen.flac import FLAC
from pathlib import Path

# Windows 控制台编码处理
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 状态文件
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flac_check_state.json')


def load_state():
    """加载已处理状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_state(state):
    """保存处理状态"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_metadata(path):
    """获取 FLAC 文件的 metadata"""
    try:
        audio = FLAC(path)
        return {
            'artist': audio.get('artist', [None])[0] or '',
            'albumartist': audio.get('albumartist', [None])[0] or ''
        }
    except Exception as e:
        return None


def check_files(root_dir, force=False):
    """检查目录下所有 FLAC 文件"""
    state = load_state()
    results = {'checked': 0, 'mismatched': 0, 'consistent': 0, 'files': {}}

    for root, dirs, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith('.flac'):
                path = os.path.join(root, f)
                rel_path = os.path.relpath(path, root_dir)

                # 跳过已处理且未强制重新检查的文件
                if not force and rel_path in state:
                    results['checked'] += 1
                    if state[rel_path].get('consistent'):
                        results['consistent'] += 1
                    else:
                        results['mismatched'] += 1
                    continue

                meta = get_metadata(path)
                if meta is None:
                    continue

                results['checked'] += 1
                is_consistent = (meta['artist'].strip().lower() == meta['albumartist'].strip().lower())

                results['files'][rel_path] = {
                    'path': path,
                    'artist': meta['artist'],
                    'albumartist': meta['albumartist'],
                    'consistent': is_consistent
                }

                if is_consistent:
                    results['consistent'] += 1
                    state[rel_path] = {'path': path, 'consistent': True, 'artist': meta['artist'], 'albumartist': meta['albumartist']}
                else:
                    results['mismatched'] += 1
                    state[rel_path] = {'path': path, 'consistent': False, 'artist': meta['artist'], 'albumartist': meta['albumartist'], 'processed': False}

    save_state(state)
    return results, state


def interactive_fix(state, root_dir="E:/music"):
    """交互式修复不一致的文件"""
    mismatched = [(k, v) for k, v in state.items() if not v.get('consistent', True)]

    if not mismatched:
        print("\n✅ 所有文件都已一致，无需处理")
        return

    print(f"\n找到 {len(mismatched)} 个不一致的文件")
    print("=" * 70)

    for i, (rel_path, info) in enumerate(mismatched, 1):
        if info.get('processed', False):
            continue

        # 获取 path，优先从 state 获取，否则尝试重建
        path = info.get('path')
        if not path:
            # 尝试从相对路径重建
            path = os.path.join(root_dir, rel_path)
            if not os.path.exists(path):
                print(f"\n[{i}/{len(mismatched)}] {rel_path}")
                print("  ⚠️ 文件路径未知且无法重建，跳过")
                continue

        artist = info['artist']
        albumartist = info['albumartist']

        print(f"\n[{i}/{len(mismatched)}] {rel_path}")
        print(f"  artist:       '{artist}'")
        print(f"  albumartist:  '{albumartist}'")

        print("\n请选择处理方式:")
        print("  1. artist -> albumartist   (用 artist 覆盖 albumartist)")
        print("  2. albumartist -> artist   (用 albumartist 覆盖 artist)")
        print("  3. 自定义 artist")
        print("  4. 自定义 albumartist")
        print("  5. 自定义两者")
        print("  6. 跳过处理 (不修改文件，下次继续询问)")
        print("  7. 视为一致 (不修改文件，下次不再询问)")
        print("  8. 退出")

        choice = input("\n请输入选项 (1-8): ").strip()

        if choice == '8':
            print("退出处理")
            break
        elif choice == '7':
            # 视为一致：标记为一致，下次不再询问
            state[rel_path] = {
                'path': path,
                'consistent': True,
                'artist': artist,
                'albumartist': albumartist,
                'processed': True
            }
            save_state(state)
            print(f"  → 视为一致 (下次不再询问)")
            continue
        elif choice == '6':
            # 跳过处理：不修改文件，但下次继续询问
            print(f"  → 跳过 (下次继续询问)")
            continue
        elif choice == '5':
            new_artist = input("    新 artist: ").strip()
            new_albumartist = input("    新 albumartist: ").strip()
        elif choice == '4':
            new_artist = artist
            new_albumartist = input("    新 albumartist: ").strip()
        elif choice == '3':
            new_artist = input("    新 artist: ").strip()
            new_albumartist = albumartist
        elif choice == '2':
            new_artist = albumartist
            new_albumartist = albumartist
        elif choice == '1':
            new_artist = artist
            new_albumartist = artist
        else:
            print("  无效选项，跳过")
            continue

        # 应用修改
        try:
            audio = FLAC(path)
            audio['artist'] = new_artist
            audio['albumartist'] = new_albumartist
            audio.save()
            print(f"  ✅ 已保存: artist='{new_artist}', albumartist='{new_albumartist}'")
            state[rel_path] = {
                'path': path,
                'consistent': new_artist.strip().lower() == new_albumartist.strip().lower(),
                'artist': new_artist,
                'albumartist': new_albumartist,
                'processed': True
            }
            save_state(state)
        except Exception as e:
            print(f"  ❌ 保存失败: {e}")


def show_summary(state):
    """显示统计摘要"""
    total = len(state)
    consistent = sum(1 for v in state.values() if v.get('consistent', True))
    mismatched = total - consistent
    processed = sum(1 for v in state.values() if v.get('processed', False))

    print("\n" + "=" * 70)
    print("📊 统计摘要")
    print("=" * 70)
    print(f"   总文件数:     {total}")
    print(f"   一致:         {consistent}")
    print(f"   不一致:       {mismatched}")
    print(f"   已处理:       {processed}")
    print(f"   待处理:       {mismatched - processed}")
    print("=" * 70)


def reset_state():
    """重置状态文件"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print("✅ 已重置状态文件")
    else:
        print("状态文件不存在")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="FLAC 元数据检查与修复工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 检查目录并显示摘要
  python flac_check.py -d "E:/music"

  # 强制重新检查所有文件
  python flac_check.py -d "E:/music" --force

  # 进入交互式修复模式
  python flac_check.py -d "E:/music" --fix

  # 重置状态
  python flac_check.py --reset
        """
    )

    parser.add_argument("-d", "--dir", help="音乐目录路径 (默认: 当前目录)")
    parser.add_argument("--force", action="store_true", help="强制重新检查所有文件")
    parser.add_argument("--fix", action="store_true", help="进入交互式修复模式")
    parser.add_argument("--reset", action="store_true", help="重置状态文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式结果")

    args = parser.parse_args()

    if args.reset:
        reset_state()
        return

    root_dir = args.dir or os.getcwd()

    print("=" * 70)
    print("🎵 FLAC 元数据检查工具")
    print("=" * 70)
    print(f"📁 目录: {root_dir}")
    print(f"🔧 模式: {'强制重新检查' if args.force else '增量检查'}")

    results, state = check_files(root_dir, force=args.force)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"\n📊 检查完成")
        print(f"   已检查: {results['checked']}")
        print(f"   一致:   {results['consistent']}")
        print(f"   不一致: {results['mismatched']}")

        show_summary(state)

    if args.fix:
        interactive_fix(state, root_dir)
        state = load_state()  # 重新加载
        show_summary(state)


if __name__ == '__main__':
    main()
