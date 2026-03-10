# Python GUI 视频转码工具实例2（支持 AVS3）

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green.svg)](https://pypi.org/project/PyQt6/)
[![ffmpeg](https://img.shields.io/badge/ffmpeg-8.0.1-red.svg)](https://ffmpeg.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

一个基于 **PyQt6** 和 **ffmpeg-python** 的图形化视频转码工具，专为高效转码 **8K 春晚 AVS3 视频** 而设计。支持 GPU
加速（NVIDIA NVENC）、批量任务管理、详细音视频参数调整，并提供友好的用户界面。

> **为什么写这个？**  
> 就是写着玩儿。所有功能用命令行基本上都能实现，但懒得每次敲命令，所以写个前端出来。如果你也懒得记 ffmpeg 参数，不妨试试这个。

---

## ✨ 功能特性

* **支持 AVS3 解码**：内置 ffmpeg 8.0.1，完美解码 8K 春晚 AVS3 视频。
* **GPU 加速**：支持 NVIDIA NVENC（H.264 / H.265），大幅提升转码速度。
* **批量任务队列**：可同时添加多个文件，设置最大并发任务数，自动排队转码。
* **详细参数调整**：
    * **视频**：编码格式（H.264/H.265/VP9/AV1/复制）、分辨率、码率、CRF、帧率、关键帧间隔、旋转/翻转等。
    * **音频**：编码格式（AAC/MP3/AC3/FLAC/Opus/复制）、采样率、比特率、声道数、音量调整。
* **编码速度预设**：针对不同编码器提供合适的预设选项（如 `medium`、`fast`、`slow`），平衡速度与质量。
* **智能输出路径**：自动生成唯一文件名，避免覆盖；支持输出到源目录或自定义文件夹。
* **实时进度显示**：任务列表中显示转码进度、输出文件大小及体积变化百分比（▲/▼ 直观表示增减）。
* **日志窗口**：记录操作和错误信息，方便排查问题。
* **拖拽添加文件**：直接将视频文件拖入窗口即可添加任务。
* **全局设置**：可配置默认 GPU 加速、并发任务数等。
* **跨平台**（主要 Windows）：代码兼容 Linux/macOS，但需自行准备 ffmpeg。

---

## 🚀 快速开始

### 1. 安装 Python 环境

要求 Python 3.8 或更高版本。

```bash
# 克隆仓库
git clone https://github.com/xumous/python-gui-video-transcoder2-example.git
cd python-gui-video-transcoder2-example

# 安装依赖
pip install PyQt6 ffmpeg-python
```

### 2. 获取 ffmpeg

本工具依赖 ffmpeg 可执行文件。你可以：

* **手动下载** ffmpeg（8.0.1 或更新版本）并将 `ffmpeg.exe`、`ffprobe.exe` 放在与脚本相同的目录，或加入系统 PATH。
* **使用打包版本**：如果你打算构建独立 EXE，将 ffmpeg 二进制文件放在打包命令指定的路径即可（见下文）。

### 3. 运行

```bash
python "python-gui-video-transcoder2-example.py"
```

---

## 📖 使用说明

### 添加任务

* 点击 **+ 新建任务** 或直接将视频文件拖入窗口。
* 在弹出对话框中设置输出格式、视频/音频参数（包括新增的 **编码速度预设**）。
* 点击 **确定** 将任务加入队列，或 **确定并开始** 立即执行。

### 任务管理

* **状态列**：显示任务状态（等待中/转码中/完成/错误）及进度条（转码中且进度为0时显示忙碌动画）。
* **操作按钮**：每个任务右侧有“删除”按钮，可单独移除。
* **批量操作**：工具栏提供“移除选定”、“清空列表”、“停止所有”、“开始所有”按钮。

### 全局设置

通过菜单 **设置 → 全局设置** 可调整：

* 默认 GPU 加速
* 自动检测视频参数
* 最大并发任务数

### 输出文件

* 输出文件默认保存在源文件目录，文件名为 `原文件名_时间戳.扩展名`。
* 完成的任务可在列表中点击文件名链接直接打开输出文件。

---

## 🛠 构建独立可执行文件

本工具支持使用 **PyInstaller** 或 **Nuitka** 打包为单个 EXE 文件，并内置 ffmpeg 二进制文件。

### 准备 ffmpeg 二进制文件

从 [ffmpeg 官网](https://ffmpeg.org/download.html) 下载 Windows 版本（建议 8.0.1
或更高），将以下三个文件放在合适的位置（例如 `C:\Java2025\`）：

* `ffmpeg.exe`
* `ffprobe.exe`
* `ffplay.exe`（可选）

### 使用 PyInstaller 打包

```powershell
python -m PyInstaller --onefile --windowed `
  --add-binary "C:\Java2025\ffmpeg.exe;." `
  --add-binary "C:\Java2025\ffprobe.exe;." `
  --add-binary "C:\Java2025\ffplay.exe;." `
  --hidden-import ffmpeg `
  --name "VideoTranscoder" `
  "python-gui-video-transcoder2-example.py"
```

### 使用 Nuitka 打包

```powershell
python -m nuitka --onefile --windows-disable-console `
  --include-data-file="C:\Java2025\ffmpeg.exe=ffmpeg.exe" `
  --include-data-file="C:\Java2025\ffprobe.exe=ffprobe.exe" `
  --include-data-file="C:\Java2025\ffplay.exe=ffplay.exe" `
  --include-module=PyQt6.sip `
  --enable-plugin=pyqt6 `
  --output-dir=dist `
  --product-name="视频转码工具" `
  --file-version="1.5.0" `
  "python-gui-video-transcoder2-example.py"
```

打包后的 EXE 文件位于 `dist` 目录，可直接运行，无需安装 Python 和 ffmpeg。

---

## 📦 依赖项

* Python ≥ 3.8
* [PyQt6](https://pypi.org/project/PyQt6/)
* [ffmpeg-python](https://pypi.org/project/ffmpeg-python/)
* ffmpeg 8.0.1（需自行下载或打包）

---

## ❓ 常见问题

### Q: 为什么我的 GPU 加速无法启用？

A: 确保你的显卡是 NVIDIA，并安装了最新的显卡驱动。GPU 加速仅支持 H.264 和 H.265 编码（对应 `h264_nvenc` / `hevc_nvenc`
）。如果仍然失败，请检查 ffmpeg 是否支持 NVENC（可用 `ffmpeg -encoders | findstr nvenc` 验证）。

### Q: 转码过程中出现错误怎么办？

A: 查看下方日志窗口，错误信息通常会提示具体原因。常见问题包括：输入文件损坏、输出路径无写入权限、ffmpeg 缺少对应编码器（如 AV1
需要额外安装 libaom-av1）。

### Q: 如何添加自定义分辨率或码率？

A: 在对应的下拉框中直接输入自定义值即可（例如 `1920x800` 或 `5000`），支持手动编辑。

### Q: 为什么任务进度停在99%？

A: 这是已知“特性”：在还有未完成的任务时，已完成的任务会显示99%进度（但实际已转完）。这是为了在视觉上区分活跃任务，后续版本可能修复。😉

### Q: 是否支持 macOS/Linux？

A: 代码本身是跨平台的，但需替换 ffmpeg 为对应平台的可执行文件。全局设置中的“系统”选项仅用于显示，不影响实际功能。

---

## 🙏 致谢

* [ffmpeg](https://ffmpeg.org/)：强大的多媒体处理工具。
* [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)：优秀的 Python GUI 框架。
* [ffmpeg-python](https://github.com/kkroening/ffmpeg-python)：Python 风格的 ffmpeg 包装器。

---

## 📄 许可证

本项目代码采用 [MIT 许可证](LICENSE)。  
ffmpeg 二进制文件遵循其自身的 [LGPL/GPL 许可证](https://ffmpeg.org/legal.html)。

---

> **注意**：本工具仅为个人无聊项目，可能存在未知 bug。如有问题欢迎提交 Issue，但懒癌发作时可能不会及时修复。  
> 最后更新：2026年3月10日（代码内日期为2026年2月26日）