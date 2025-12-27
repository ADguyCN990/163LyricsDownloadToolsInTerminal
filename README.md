# Music Lyrics Downloader CLI Tools

一个用于从网易云音乐下载歌词的CLI工具集，支持双语歌词（原文+译文）。

## 功能特性

### scan_music.py

| 功能 | 说明 |
|------|------|
| 递归扫描 | 支持扫描目录下所有音乐文件（含子目录） |
| 音频元数据 | 读取MP3/FLAC/M4A等格式的艺术家、专辑、时长信息 |
| 智能清洗 | 自动去除文件名中的版本信息、比特率等干扰字符 |
| 网易云搜索 | 用文件名+元数据组合搜索网易云音乐 |
| 相似度计算 | 计算匹配结果的可信度 |
| 结果输出 | 生成JSON详细报告和ID列表文件 |

### lyric_cli.py

| 功能 | 说明 |
|------|------|
| WeAPI加密 | 使用官方加密协议，稳定获取翻译歌词 |
| 单曲下载 | 支持网易云音乐链接或ID |
| 批量下载 | 从文件读取多个链接/ID |
| 专辑/歌单 | 自动下载整个专辑或歌单的歌词 |
| 双语歌词 | 支持原文和译文合并保存 |
| LRC格式 | 标准LRC歌词文件输出 |
| 错误重试 | API限流时自动重试 |

## 安装

```bash
# 克隆项目
git clone https://github.com/yourusername/lyrics.git
cd lyrics

# 安装依赖
pip install pycryptodome mutagen
```

## 依赖

- Python 3.8+
- pycryptodome - AES/RSA加密
- mutagen - 音频文件元数据读取

## 使用方法

### 1. 扫描音乐文件

扫描音乐目录，获取网易云音乐ID：

```bash
# 基本用法
python scan_music.py -d ./music -o results.json

# 不扫描子目录
python scan_music.py -d ./music --no-recursive -o results.json

# 禁用元数据验证（仅使用文件名）
python scan_music.py -d ./music --no-metadata -o results.json
```

**输出文件：**

- `results.json` - 详细搜索结果（JSON格式）
- `results.ids.txt` - ID列表（供lyric_cli.py使用）

### 2. 下载歌词

使用ID列表下载歌词：

```bash
# 从ID列表文件下载
python lyric_cli.py -f results.ids.txt -o ./lyrics

# 直接输入单曲链接
python lyric_cli.py "https://music.163.com/#/song?id=347230" -o ./lyrics

# 批量链接
python lyric_cli.py "347230" "32507038" -o ./lyrics

# 下载专辑
python lyric_cli.py "https://music.163.com/#/album?id=325199" -o ./lyrics

# 只下载原文歌词
python lyric_cli.py -f results.ids.txt -m original -o ./lyrics

# 只保存译文
python lyric_cli.py -f results.ids.txt -m translated -o ./lyrics

# 增加请求间隔（避免API限流）
python lyric_cli.py -f results.ids.txt -o ./lyrics -d 2.0
```

### 完整工作流

```bash
# 1. 扫描音乐目录
python scan_music.py -d "E:\Music" -o scan_results.json

# 2. 下载歌词到指定目录
python lyric_cli.py -f scan_results.ids.txt -o "E:\Lyrics"
```

## 命令行参数

### scan_music.py

```
-d, --dir DIR       音乐目录路径 (必填)
-o, --output FILE   输出JSON文件路径 (默认: scan_results.json)
-r, --recursive     递归扫描子目录 (默认: 开启)
--no-recursive      不扫描子目录
-t, --threshold     相似度阈值 0-1 (默认: 0.6)
--no-metadata       禁用音频元数据验证
```

### lyric_cli.py

```
inputs              歌曲链接或ID（可多个）
-f, --file FILE     批量输入文件（每行一个链接）
-o, --output DIR    输出目录 (默认: ./lyrics)
-m, --merge         歌词合并模式:
                    - original: 只保存原文
                    - translated: 只保存译文
                    - both: 中英双语合并 (默认)
-d, --delay         请求间隔秒数 (默认: 1.0)
```

## 输出示例

### scan_music.py 输出

```json
{
  "timestamp": "2025-12-27 10:00:00",
  "total_files": 10,
  "success_count": 9,
  "skipped_count": 1,
  "results": [
    {
      "file": "/music/海阔天空 - Beyond.mp3",
      "search_name": "海阔天空 Beyond",
      "song_id": 347230,
      "song_name": "海阔天空",
      "artist": "Beyond",
      "confidence": "high",
      "metadata": {
        "local_artist": "Beyond",
        "local_album": "乐与怒",
        "local_title": "海阔天空"
      }
    }
  ],
  "skipped": []
}
```

### lyric_cli.py 输出（双语LRC）

```lrc
[ti:Love Story]
[ar:Taylor Swift]
[al:Fearless]
[by:163MusicLyrics-CLI]
[offset:0]

[00:16.240]We were young when I first saw you
[00:16.240]第一次见到你的时候我们都还很年轻
[00:20.050]I close my eyes and the flashback starts
[00:20.050]我闭上眼睛 我们的故事在我脑海里一幕幕回放
[00:23.650]I'm standing there
[00:23.650]我站在那里
```

**输出文件名格式：** `<歌曲名> - <艺术家名>.lrc`
例如：`Love Story - Taylor Swift.lrc`

## 支持的音乐格式

```
.mp3  .flac  .wav  .m4a  .aac  .ogg
.ape  .wma  .dsf  .dff  .alac  .opus
```

## 技术实现

### WeAPI 加密

工具使用网易云音乐官方 WeAPI 协议，通过 AES-CBC + RSA 加密与服务器通信：

- **netease_crypto.py** - 加密模块
  - `aes_encode()` - AES-128-CBC 加密
  - `rsa_encode()` - RSA 加密
  - `weapi_encrypt()` - 封装加密流程

### API 限流处理

当遇到 API 限流（HTTP 405/429/503）时，工具会自动：
1. 指数级增加等待时间（2秒 → 4秒 → 8秒）
3. 最多重试 3 次
4. 超过次数后跳过当前歌曲，继续处理下一个

## 注意事项

1. **请求频率**：默认请求间隔1秒，可通过 `-d` 参数调整
2. **相似度**：建议阈值设为0.6-0.8，过低可能导致匹配错误
3. **版权问题**：部分歌曲可能没有歌词或版权限制无法下载
4. **翻译获取**：使用 WeAPI 加密后可获取大部分歌曲的译文翻译

## License

MIT License

## 感谢

- [网易云音乐API](https://github.com/Binaryify/NeteaseCloudMusicApi)
- 原始项目 [163MusicLyrics](https://github.com/jitwxs/163MusicLyrics)
