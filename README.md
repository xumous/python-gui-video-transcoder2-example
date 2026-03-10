# python-gui-video-transcoder2-example

A simple example 2 of a video transcoder with a graphical user interface built in Python. Demonstrates basic video
format conversion using FFmpeg, ideal for learning how to integrate GUI frameworks like PyQt with multimedia processing.

# Python GUI Video Transcoder 2 Example (AVS3 Support)

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green.svg)](https://pypi.org/project/PyQt6/)
[![ffmpeg](https://img.shields.io/badge/ffmpeg-8.0.1-red.svg)](https://ffmpeg.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A graphical video transcoding tool based on **PyQt6** and **ffmpeg-python**, designed for efficiently transcoding **8K
Spring Festival Gala AVS3 videos**. It supports GPU acceleration (NVIDIA NVENC), batch task management, detailed
audio/video parameter adjustments, and provides a user-friendly interface.

> **Why write this?**  
> Just for fun. All functions can basically be achieved via command line, but I'm too lazy to type commands every time,
> so I wrote a frontend. If you're also too lazy to memorize ffmpeg parameters, give this a try.

---

## ✨ Features

* **AVS3 Decoding Support**: Built-in ffmpeg 8.0.1, perfectly decodes 8K Spring Festival Gala AVS3 videos.
* **GPU Acceleration**: Supports NVIDIA NVENC (H.264 / H.265), greatly speeding up transcoding.
* **Batch Task Queue**: Add multiple files at once, set maximum concurrent tasks, automatic queuing and transcoding.
* **Detailed Parameter Adjustments**:
    * **Video**: Encoding format (H.264/H.265/VP9/AV1/Copy), resolution, bitrate, CRF, framerate, keyframe interval,
      rotation/flip, etc.
    * **Audio**: Encoding format (AAC/MP3/AC3/FLAC/Opus/Copy), sample rate, bitrate, channels, volume adjustment.
* **Encoding Speed Presets**: Provides appropriate preset options (e.g., `medium`, `fast`, `slow`) for different
  encoders to balance speed and quality.
* **Smart Output Path**: Automatically generates unique filenames to avoid overwriting; supports output to source
  directory or custom folder.
* **Real-time Progress Display**: Shows transcoding progress, output file size, and volume change percentage (▲/▼ for
  intuitive indication) in the task list.
* **Log Window**: Records operations and error messages for easy troubleshooting.
* **Drag & Drop Files**: Simply drag video files into the window to add tasks.
* **Global Settings**: Configurable default GPU acceleration, number of concurrent tasks, etc.
* **Cross-platform** (primarily Windows): Code is compatible with Linux/macOS, but you need to provide ffmpeg yourself.

---

## 🚀 Quick Start

### 1. Install Python Environment

Requires Python 3.8 or higher.

```bash
# Clone repository
git clone https://github.com/xumous/python-gui-video-transcoder2-example.git
cd python-gui-video-transcoder2-example

# Install dependencies
pip install PyQt6 ffmpeg-python
```

### 2. Obtain ffmpeg

This tool depends on the ffmpeg executable. You can:

* **Manually download** ffmpeg (8.0.1 or newer) and place `ffmpeg.exe`, `ffprobe.exe` in the same directory as the
  script, or add them to your system PATH.
* **Use the packaged version**: If you plan to build a standalone EXE, place the ffmpeg binaries in the path specified
  in the packaging command (see below).

### 3. Run

```bash
python "python-gui-video-transcoder2-example.py"
```

---

## 📖 Usage Instructions

### Adding Tasks

* Click **+ New Task** or drag video files directly into the window.
* In the pop-up dialog, set output format, video/audio parameters (including the new **Encoding Speed Preset**).
* Click **OK** to add the task to the queue, or **OK & Start** to execute immediately.

### Task Management

* **Status Column**: Displays task status (Waiting/Transcoding/Completed/Error) and a progress bar (shows busy animation
  when transcoding with 0% progress).
* **Action Buttons**: Each task has a "Delete" button on the right for individual removal.
* **Batch Operations**: Toolbar provides "Remove Selected", "Clear List", "Stop All", "Start All" buttons.

### Global Settings

Via menu **Settings → Global Settings**, you can adjust:

* Default GPU acceleration
* Auto-detect video parameters
* Maximum concurrent tasks

### Output Files

* Output files are saved in the source file directory by default, with filename `original_filename_timestamp.extension`.
* Upon completion, you can click the filename link in the list to directly open the output file.

---

## 🛠 Building a Standalone Executable

This tool supports packaging into a single EXE file using **PyInstaller** or **Nuitka**, with ffmpeg binaries embedded.

### Prepare ffmpeg Binaries

Download the Windows version from [ffmpeg official site](https://ffmpeg.org/download.html) (recommend 8.0.1 or higher),
and place the following three files in a suitable location (e.g., `C:\Java2025\`):

* `ffmpeg.exe`
* `ffprobe.exe`
* `ffplay.exe` (optional)

### Packaging with PyInstaller

```powershell
python -m PyInstaller --onefile --windowed `
  --add-binary "C:\Java2025\ffmpeg.exe;." `
  --add-binary "C:\Java2025\ffprobe.exe;." `
  --add-binary "C:\Java2025\ffplay.exe;." `
  --hidden-import ffmpeg `
  --name "VideoTranscoder" `
  "python-gui-video-transcoder2-example.py"
```

### Packaging with Nuitka

```powershell
python -m nuitka --onefile --windows-disable-console `
  --include-data-file="C:\Java2025\ffmpeg.exe=ffmpeg.exe" `
  --include-data-file="C:\Java2025\ffprobe.exe=ffprobe.exe" `
  --include-data-file="C:\Java2025\ffplay.exe=ffplay.exe" `
  --include-module=PyQt6.sip `
  --enable-plugin=pyqt6 `
  --output-dir=dist `
  --product-name="Video Transcoder" `
  --file-version="1.5.0" `
  "python-gui-video-transcoder2-example.py"
```

The packaged EXE file will be in the `dist` directory and can be run directly without installing Python and ffmpeg.

---

## 📦 Dependencies

* Python ≥ 3.8
* [PyQt6](https://pypi.org/project/PyQt6/)
* [ffmpeg-python](https://pypi.org/project/ffmpeg-python/)
* ffmpeg 8.0.1 (needs to be downloaded or packaged manually)

---

## ❓ FAQ

### Q: Why can't I enable GPU acceleration?

A: Make sure your graphics card is NVIDIA and you have the latest drivers installed. GPU acceleration only supports
H.264 and H.265 encoding (`h264_nvenc` / `hevc_nvenc`). If it still fails, check if your ffmpeg supports NVENC (verify
with `ffmpeg -encoders | findstr nvenc`).

### Q: What should I do if an error occurs during transcoding?

A: Check the log window below; error messages usually indicate the specific cause. Common issues include: corrupted
input file, no write permission for output path, ffmpeg missing the required encoder (e.g., AV1 needs libaom-av1
installed).

### Q: How do I add custom resolution or bitrate?

A: Simply type the custom value directly into the corresponding combo box (e.g., `1920x800` or `5000`); manual editing
is supported.

### Q: Why does the task progress stay at 99%?

A: This is a known "feature": when there are still unfinished tasks, completed tasks will show 99% progress (though they
are actually finished). This is to visually distinguish active tasks; may be fixed in future versions. 😉

### Q: Does it support macOS/Linux?

A: The code itself is cross-platform, but you need to replace ffmpeg with the executable for your platform. The "System"
option in global settings is for display only and does not affect functionality.

---

## 🙏 Acknowledgements

* [ffmpeg](https://ffmpeg.org/): Powerful multimedia processing tool.
* [PyQt6](https://www.riverbankcomputing.com/software/pyqt/): Excellent Python GUI framework.
* [ffmpeg-python](https://github.com/kkroening/ffmpeg-python): Pythonic wrapper for ffmpeg.

---

## 📄 License

The code of this project is licensed under the [MIT License](LICENSE).  
ffmpeg binaries are subject to their own [LGPL/GPL licenses](https://ffmpeg.org/legal.html).

---

> **Note**: This tool is just a personal fun project, and there may be unknown bugs. Feel free to submit issues, but
> they may not be fixed promptly due to laziness.  
> Last updated: March 10, 2026 (code date: February 26, 2026)