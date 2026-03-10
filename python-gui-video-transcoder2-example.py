#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频转码工具（支持AVS3）
使用 PyQt6 + ffmpeg-python
支持任务队列、全局设置、视频/音频详细参数、拖拽添加、GPU加速等
新增：编码速度预设（软件/硬件编码器专用）
"""
import sys
import os
import re
import subprocess
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Callable
# PyQt6 导入
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLabel, QFileDialog, QDialog, QFormLayout, QGroupBox,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit,
    QDialogButtonBox, QMessageBox, QProgressBar, QMenu, QAbstractItemView,
    QSplitter, QTextEdit, QFrame, QSizePolicy, QGridLayout, QTabWidget,
    QScrollArea, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QUrl, QSettings, QTimer, QMutex, QMutexLocker,
    QObject, QRunnable, QThreadPool, pyqtSlot, Q_ARG, QMetaObject
)
from PyQt6.QtGui import (
    QDesktopServices, QDragEnterEvent, QDropEvent, QFont, QIcon, QAction
)
# FFmpeg 库
import ffmpeg


# ------------------ 打包环境下的 ffmpeg 路径重定向 ------------------
def get_ffmpeg_path():
    """获取打包后的ffmpeg路径（优先使用打包目录下的文件）"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        ffmpeg_exe = os.path.join(base_path, 'ffmpeg.exe')
        ffprobe_exe = os.path.join(base_path, 'ffprobe.exe')
        if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
            return ffmpeg_exe, ffprobe_exe
    return None, None


def setup_ffmpeg_environment():
    """设置FFmpeg环境：将ffmpeg目录加入PATH，并通知ffmpeg-python"""
    ffmpeg_exe, ffprobe_exe = get_ffmpeg_path()
    if ffmpeg_exe:
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)
        # 将目录添加到PATH开头，使DLL能被找到
        current_path = os.environ.get('PATH', '')
        if ffmpeg_dir not in current_path.split(os.pathsep):
            os.environ['PATH'] = ffmpeg_dir + os.pathsep + current_path
        # 设置ffmpeg-python使用的路径
        ffmpeg._ffmpeg = ffmpeg_exe
        ffmpeg._ffprobe = ffprobe_exe
    else:
        # 无打包FFmpeg，使用系统PATH中的（通常不支持AVS3）
        pass


# 在程序入口调用环境设置
setup_ffmpeg_environment()

# ==================== 常量定义 ====================
SETTINGS_FILE = "video_transcoder.ini"
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts'}

DEFAULT_SETTINGS = {
    "gpu_acceleration": False,
    "auto_detect": True,
    "ha_test": False,
    "system": "Windows",
    "max_concurrent_tasks": 3,
}

CODEC_MAP = {
    "HEVC (H.265)": "libx265",
    "H.264": "libx264",
    "VP9": "libvpx-vp9",
    "AV1": "libaom-av1",
    "Copy": "copy"
}

GPU_CODEC_MAP = {
    "HEVC (H.265)": "hevc_nvenc",
    "H.264": "h264_nvenc",
}

AUDIO_CODEC_MAP = {
    "AAC": "aac",
    "MP3": "libmp3lame",
    "AC3": "ac3",
    "FLAC": "flac",
    "Opus": "libopus",
    "Copy": "copy"
}

# 编码速度预设支持列表（用于动态更新下拉框）
SOFTWARE_PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
NVENC_PRESETS = ["fast", "medium", "slow", "hq", "llhq"]
QSV_PRESETS = ["veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
AMF_PRESETS = ["speed", "balanced", "quality"]


# ==================== 工具函数 ====================
def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"


def percent_arrow(percent: float) -> str:
    """百分比增减箭头"""
    if percent > 0:
        return f"▲ +{percent:.1f}%"
    elif percent < 0:
        return f"▼ {percent:.1f}%"
    else:
        return "▬ 0.0%"


def get_video_duration(filepath: str) -> Optional[float]:
    """获取视频时长（秒）"""
    try:
        probe = ffmpeg.probe(filepath)
        video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
        if video_stream and 'duration' in video_stream:
            return float(video_stream['duration'])
        audio_stream = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), None)
        if audio_stream and 'duration' in audio_stream:
            return float(audio_stream['duration'])
        if 'format' in probe and 'duration' in probe['format']:
            return float(probe['format']['duration'])
    except Exception:
        pass
    return None


def is_video_file(filepath: str) -> bool:
    """检查是否为视频文件"""
    return Path(filepath).suffix.lower() in VIDEO_EXTENSIONS


def generate_output_path(params: 'TranscodeParams', base_timestamp: str = None) -> Path:
    """根据参数生成输出路径（基础版本，不含冲突检查）"""
    in_file = Path(params.input_file)
    out_format = params.output_format.lower()
    if params.output_folder == "输出到源文件目录":
        out_dir = in_file.parent
    else:
        out_dir = Path(params.output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    if base_timestamp is None:
        base_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{in_file.stem}_{base_timestamp}.{out_format}"
    return out_dir / out_name


# ==================== 数据类 ====================
@dataclass
class TranscodeParams:
    """转码参数数据类"""
    input_file: str
    output_format: str = "mp4"
    video_codec: str = "HEVC (H.265)"
    resolution: str = "默认（原视频尺寸）"
    bitrate: str = "默认（16000）"
    crf: str = "关闭"
    gpu: bool = False
    fps: str = "默认（原视频）"
    aspect: str = "自动（原视频）"
    twopass: str = "否"
    keyint: str = "默认"
    rotate: str = "否"
    hflip: str = "否"
    vflip: str = "否"
    audio_codec: str = "AAC"
    audio_rate: str = "默认（原视频）"
    audio_bitrate: str = "默认（320）"
    audio_channels: str = "默认（2）"
    volume: float = 100.0
    copy_streams: bool = True
    output_folder: str = "输出到源文件目录"
    # 新增编码速度预设字段
    preset: str = "medium"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskInfo:
    """任务信息数据类"""
    id: int
    params: TranscodeParams
    output_path: str = None  # 确定的输出路径
    status: str = "等待中"
    progress: int = 0
    output_file: Optional[str] = None
    output_size: int = 0
    percent_change: float = 0.0
    error_msg: str = ""


# ==================== 工作线程 ====================
class WorkerSignals(QObject):
    """工作线程信号"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    started = pyqtSignal()


class FFmpegWorker(QRunnable):
    """FFmpeg转码工作线程（使用QRunnable避免QThread闪退问题）"""

    def __init__(self, task_id: int, params: TranscodeParams, output_path: str):
        super().__init__()
        self.task_id = task_id
        self.params = params
        self.output_path = output_path
        self.signals = WorkerSignals()
        self.process: Optional[subprocess.Popen] = None
        self._is_running = True
        self._mutex = QMutex()
        self.setAutoDelete(True)

    def stop(self):
        """停止任务"""
        with QMutexLocker(self._mutex):
            self._is_running = False
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                except Exception:
                    pass

    def is_running(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._is_running

    @pyqtSlot()
    def run(self):
        """执行转码任务"""
        try:
            self.signals.started.emit()
            result = self._do_transcode()
            if result:
                self.signals.finished.emit(result)
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.signals.error.emit(f"转码异常: {str(e)}\n{error_detail}")

    def _do_transcode(self) -> Optional[dict]:
        """执行实际的转码操作"""
        input_path = self.params.input_file
        in_file = Path(input_path)
        out_path = Path(self.output_path)

        if not in_file.exists():
            self.signals.error.emit(f"输入文件不存在: {input_path}")
            return None

        # 确保输出目录存在
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 尝试通过ffprobe获取时长（可能失败）
        total_duration = get_video_duration(str(in_file))

        # 构建ffmpeg命令
        try:
            cmd = self._build_ffmpeg_command(str(in_file), str(out_path))
        except Exception as e:
            self.signals.error.emit(f"构建命令失败: {str(e)}")
            return None

        # 获取FFmpeg路径和目录（用于设置cwd）
        ffmpeg_exe, _ = get_ffmpeg_path()
        if not ffmpeg_exe:
            ffmpeg_exe = 'ffmpeg'  # 回退到系统PATH
            ffmpeg_dir = None
        else:
            ffmpeg_dir = os.path.dirname(ffmpeg_exe)
            cmd[0] = ffmpeg_exe  # 使用绝对路径

        # 执行ffmpeg
        try:
            # 安全获取 CREATE_NO_WINDOW 标志
            if sys.platform == "win32":
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            else:
                creationflags = 0

            # 启动进程，设置工作目录为ffmpeg所在目录（确保DLL被找到）
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore',
                bufsize=1,
                creationflags=creationflags,
                cwd=ffmpeg_dir
            )

            # 增强的正则表达式，支持1-2位小时
            time_pattern = re.compile(r'(?:out_)?time=(\d{1,2}):(\d{2}):(\d{2}\.\d+)')
            # 用于从ffmpeg输出中解析总时长的正则（同样支持可变小时）
            duration_pattern = re.compile(r'Duration: (\d{1,2}):(\d{2}):(\d{2}\.\d+)')

            while self.is_running():
                line = self.process.stderr.readline()
                if not line:
                    if self.process.poll() is not None:
                        break
                    continue

                # 如果尚未获得总时长，尝试从输出中解析 Duration: 行
                if total_duration is None:
                    dur_match = duration_pattern.search(line)
                    if dur_match:
                        h, m, s = map(float, dur_match.groups())
                        total_duration = h * 3600 + m * 60 + s
                        # 此时可能已经有进度行被错过了，但没关系，后面会继续解析

                # 解析进度
                if total_duration is not None and total_duration > 0:
                    match = time_pattern.search(line)
                    if match:
                        h, m, s = map(float, match.groups())
                        current_time = h * 3600 + m * 60 + s
                        percent = int((current_time / total_duration) * 100)
                        percent = max(0, min(99, percent))
                        self.signals.progress.emit(percent)

            # 等待进程结束
            retcode = self.process.wait()

            if not self.is_running():
                # 用户手动停止
                if out_path.exists():
                    out_path.unlink()
                self.signals.error.emit("任务已取消")
                return None

            if retcode != 0:
                error_output = self.process.stderr.read() if self.process.stderr else ""
                if out_path.exists():
                    out_path.unlink()
                self.signals.error.emit(f"转码失败 (错误码 {retcode}): {error_output[:500]}")
                return None

            # 转码成功
            if not out_path.exists():
                self.signals.error.emit("输出文件未生成")
                return None

            out_size = out_path.stat().st_size
            in_size = in_file.stat().st_size
            percent_change = ((out_size - in_size) / in_size) * 100 if in_size > 0 else 0

            return {
                "task_id": self.task_id,
                "input_file": str(in_file),
                "output_file": str(out_path),
                "output_size": out_size,
                "percent_change": percent_change,
                "status": "完成"
            }

        except Exception as e:
            if out_path.exists():
                out_path.unlink()
            raise e

    def _build_ffmpeg_command(self, input_path: str, output_path: str) -> list:
        """构建ffmpeg命令"""
        cmd = ['ffmpeg', '-y', '-i', input_path]

        # 视频编码器
        vcodec = CODEC_MAP.get(self.params.video_codec, "libx265")
        if self.params.gpu and self.params.video_codec in GPU_CODEC_MAP:
            vcodec = GPU_CODEC_MAP[self.params.video_codec]

        if vcodec == "copy":
            cmd.extend(['-c:v', 'copy'])
        else:
            cmd.extend(['-c:v', vcodec])

            # 添加编码速度预设（仅对支持的编码器）
            preset_supported_codecs = {
                'libx264', 'libx265',
                'hevc_nvenc', 'h264_nvenc',
                'hevc_qsv', 'h264_qsv',
                'hevc_amf', 'h264_amf'
            }
            if vcodec in preset_supported_codecs:
                cmd.extend(['-preset', self.params.preset])
            # 注意：VP9/AV1等使用其他参数，暂不处理，留待后续扩展

            # CRF（优先于码率）
            if self.params.crf != "关闭":
                try:
                    crf_val = int(self.params.crf)
                    cmd.extend(['-crf', str(crf_val)])
                except ValueError:
                    pass
            else:
                # 码率
                if self.params.bitrate != "默认（16000）":
                    try:
                        br = int(self.params.bitrate.replace('k', '').replace('K', ''))
                        cmd.extend(['-b:v', f"{br}k"])
                    except ValueError:
                        pass

            # 分辨率
            if self.params.resolution != "默认（原视频尺寸）":
                m = re.search(r"(\d+)x(\d+)", self.params.resolution)
                if m:
                    w, h = m.groups()
                    cmd.extend(['-vf', f"scale={w}:{h}"])

            # 帧率
            if self.params.fps != "默认（原视频）":
                try:
                    fps = int(self.params.fps)
                    cmd.extend(['-r', str(fps)])
                except ValueError:
                    pass

            # 关键帧间隔
            if self.params.keyint != "默认":
                try:
                    keyint = int(self.params.keyint)
                    cmd.extend(['-g', str(keyint)])
                except ValueError:
                    pass

        # 音频设置
        acodec = AUDIO_CODEC_MAP.get(self.params.audio_codec, "aac")
        if acodec == "copy":
            cmd.extend(['-c:a', 'copy'])
        else:
            cmd.extend(['-c:a', acodec])

            # 采样率
            if self.params.audio_rate != "默认（原视频）":
                try:
                    ar = int(self.params.audio_rate)
                    cmd.extend(['-ar', str(ar)])
                except ValueError:
                    pass

            # 音频码率
            if self.params.audio_bitrate != "默认（320）":
                try:
                    abr = int(self.params.audio_bitrate.replace('k', '').replace('K', ''))
                    cmd.extend(['-b:a', f"{abr}k"])
                except ValueError:
                    pass

            # 声道
            if self.params.audio_channels != "默认（2）":
                try:
                    ch = int(self.params.audio_channels)
                    cmd.extend(['-ac', str(ch)])
                except ValueError:
                    pass

            # 音量（修正：正确合并到音频滤镜 -af 中）
            if self.params.volume != 100.0:
                vol = self.params.volume / 100.0
                # 检查是否已存在音频滤镜
                af_index = None
                for i, arg in enumerate(cmd):
                    if arg == '-af':
                        af_index = i
                        break
                if af_index is not None:
                    # 已有 -af，追加滤镜
                    cmd[af_index + 1] = f"{cmd[af_index + 1]},volume={vol}"
                else:
                    # 无音频滤镜，新增 -af
                    cmd.extend(['-af', f"volume={vol}"])

        # 输出格式
        cmd.extend(['-f', self.params.output_format.lower()])

        # 输出路径
        cmd.append(output_path)

        return cmd


# ==================== 任务管理器 ====================
class TaskManager(QObject):
    """任务管理器（单例）"""
    task_added = pyqtSignal(object)  # TaskInfo
    task_updated = pyqtSignal(object)  # dict
    task_removed = pyqtSignal(int)  # task_id
    all_stopped = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.settings = QSettings(SETTINGS_FILE, QSettings.Format.IniFormat)
        self.tasks: Dict[int, TaskInfo] = {}
        self.workers: Dict[int, FFmpegWorker] = {}
        self.task_counter = 0
        self._mutex = QMutex()
        self._thread_pool = QThreadPool()
        self._update_max_threads()

    def _update_max_threads(self):
        """更新线程池最大线程数"""
        max_threads = self.settings.value("max_concurrent_tasks", 3, type=int)
        self._thread_pool.setMaxThreadCount(max(max_threads, 1))

    def _resolve_output_path(self, params: TranscodeParams) -> str:
        """生成唯一的输出路径（避免与现有任务或文件冲突）"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_path = generate_output_path(params, timestamp)
        out_path = base_path
        counter = 1

        # 获取所有进行中的任务输出路径（不包括已完成/错误的任务，因为这些任务的输出文件可能已被删除，但我们会检查文件存在性）
        active_paths = set()
        for task in self.tasks.values():
            if task.status not in ["完成", "错误"] and task.output_path:
                active_paths.add(task.output_path)

        # 如果路径已存在（文件存在或被其他活跃任务占用），则增加后缀
        while out_path.exists() or str(out_path) in active_paths:
            stem = base_path.stem
            new_stem = f"{stem}_{counter}"
            out_path = base_path.with_stem(new_stem)
            counter += 1

        return str(out_path)

    def add_task(self, params: TranscodeParams) -> int:
        """添加任务"""
        with QMutexLocker(self._mutex):
            self.task_counter += 1
            task_id = self.task_counter
            # 生成唯一输出路径
            output_path = self._resolve_output_path(params)
            task = TaskInfo(id=task_id, params=params, output_path=output_path)
            self.tasks[task_id] = task

        self.task_added.emit(task)
        return task_id

    def start_task(self, task_id: int):
        """启动单个任务"""
        with QMutexLocker(self._mutex):
            if task_id not in self.tasks:
                return
            task = self.tasks[task_id]
            if task.status not in ["等待中", "错误", "已停止"]:
                return

            task.status = "转码中"
            task.progress = 0
            task.error_msg = ""

        self.task_updated.emit({"id": task_id, "status": "转码中", "progress": 0})

        # 创建工作线程
        worker = FFmpegWorker(task_id, task.params, task.output_path)
        worker.signals.progress.connect(lambda p, tid=task_id: self._on_progress(tid, p))
        worker.signals.finished.connect(lambda r, tid=task_id: self._on_finished(tid, r))
        worker.signals.error.connect(lambda e, tid=task_id: self._on_error(tid, e))

        with QMutexLocker(self._mutex):
            self.workers[task_id] = worker

        self._thread_pool.start(worker)

    def start_all_pending(self):
        """启动所有等待中的任务"""
        self._update_max_threads()
        with QMutexLocker(self._mutex):
            pending_tasks = [
                tid for tid, task in self.tasks.items()
                if task.status == "等待中"
            ]

        for task_id in pending_tasks:
            self.start_task(task_id)

    def stop_task(self, task_id: int):
        """停止单个任务"""
        with QMutexLocker(self._mutex):
            if task_id in self.workers:
                self.workers[task_id].stop()
            if task_id in self.tasks:
                task = self.tasks[task_id]
                if task.status == "转码中":
                    task.status = "已停止"
                    task.progress = 0

        self.task_updated.emit({"id": task_id, "status": "已停止", "progress": 0})

    def stop_all_tasks(self):
        """停止所有任务"""
        with QMutexLocker(self._mutex):
            for task_id, worker in self.workers.items():
                worker.stop()
            for task in self.tasks.values():
                if task.status == "转码中":
                    task.status = "已停止"
                    task.progress = 0

        self.all_stopped.emit()

    def remove_task(self, task_id: int):
        """移除任务"""
        self.stop_task(task_id)

        with QMutexLocker(self._mutex):
            if task_id in self.tasks:
                del self.tasks[task_id]
            if task_id in self.workers:
                del self.workers[task_id]

        self.task_removed.emit(task_id)

    def clear_all_tasks(self):
        """清空所有任务"""
        self.stop_all_tasks()

        with QMutexLocker(self._mutex):
            self.tasks.clear()
            self.workers.clear()
            self.task_counter = 0

        self.all_stopped.emit()

    def _on_progress(self, task_id: int, progress: int):
        """进度更新"""
        with QMutexLocker(self._mutex):
            if task_id in self.tasks:
                self.tasks[task_id].progress = progress

        self.task_updated.emit({"id": task_id, "progress": progress})

    def _on_finished(self, task_id: int, result: dict):
        """任务完成"""
        with QMutexLocker(self._mutex):
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.status = "完成"
                task.progress = 100
                task.output_file = result.get("output_file")
                task.output_size = result.get("output_size", 0)
                task.percent_change = result.get("percent_change", 0.0)

            if task_id in self.workers:
                del self.workers[task_id]

        self.task_updated.emit(result)

    def _on_error(self, task_id: int, error_msg: str):
        """任务错误"""
        with QMutexLocker(self._mutex):
            if task_id in self.tasks:
                self.tasks[task_id].status = "错误"
                self.tasks[task_id].error_msg = error_msg
                self.tasks[task_id].progress = 0

            if task_id in self.workers:
                del self.workers[task_id]

        self.task_updated.emit({"id": task_id, "status": "错误", "error": error_msg})

    def get_task(self, task_id: int) -> Optional[TaskInfo]:
        """获取任务信息"""
        with QMutexLocker(self._mutex):
            return self.tasks.get(task_id)


# ==================== 全局设置对话框 ====================
class GlobalSettingsDialog(QDialog):
    """全局设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局设置")
        self.resize(450, 350)
        self.settings = QSettings(SETTINGS_FILE, QSettings.Format.IniFormat)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 设置组
        settings_group = QGroupBox("基本设置")
        form_layout = QFormLayout(settings_group)

        # GPU加速
        self.gpu_check = QCheckBox("启用GPU加速（需要NVIDIA显卡）")
        form_layout.addRow(self.gpu_check)

        # 自动检测
        self.auto_check = QCheckBox("自动检测视频参数")
        self.auto_check.setToolTip("添加文件时自动检测视频信息")
        form_layout.addRow(self.auto_check)

        # HA Test
        self.ha_check = QCheckBox("HA Test（硬件加速测试）")
        self.ha_check.setToolTip("测试硬件加速兼容性")
        form_layout.addRow(self.ha_check)

        # 系统
        self.system_combo = QComboBox()
        self.system_combo.addItems(["Windows", "macOS", "Linux"])
        self.system_combo.setEnabled(False)  # 只读
        form_layout.addRow("系统:", self.system_combo)

        # 多线程
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 10)
        self.thread_spin.setSuffix(" 个")
        self.thread_spin.setToolTip("同时转码的任务数量（1-10）")
        form_layout.addRow("使用多线程:", self.thread_spin)

        layout.addWidget(settings_group)

        # 说明
        note_label = QLabel("注意：GPU加速需要NVIDIA显卡并安装最新驱动")
        note_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(note_label)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()

        self.reset_btn = QPushButton("重设")
        self.reset_btn.setToolTip("重新加载已保存的设置")
        self.reset_btn.clicked.connect(self._reset_settings)

        self.default_btn = QPushButton("默认")
        self.default_btn.setToolTip("恢复默认设置")
        self.default_btn.clicked.connect(self._default_settings)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)

        self.apply_btn = QPushButton("应用")
        self.apply_btn.setToolTip("应用设置但不关闭窗口")
        self.apply_btn.clicked.connect(self._apply_settings)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._accept_settings)

        btn_layout.addWidget(self.reset_btn)
        btn_layout.addWidget(self.default_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)

    def _load_settings(self):
        """加载设置"""
        self.gpu_check.setChecked(self.settings.value("gpu_acceleration", False, type=bool))
        self.auto_check.setChecked(self.settings.value("auto_detect", True, type=bool))
        self.ha_check.setChecked(self.settings.value("ha_test", False, type=bool))
        self.system_combo.setCurrentText(self.settings.value("system", "Windows"))
        self.thread_spin.setValue(self.settings.value("max_concurrent_tasks", 3, type=int))

    def _reset_settings(self):
        """重设"""
        self.settings.sync()
        self._load_settings()
        QMessageBox.information(self, "重设", "已重新加载保存的设置")

    def _default_settings(self):
        """默认"""
        self.gpu_check.setChecked(DEFAULT_SETTINGS["gpu_acceleration"])
        self.auto_check.setChecked(DEFAULT_SETTINGS["auto_detect"])
        self.ha_check.setChecked(DEFAULT_SETTINGS["ha_test"])
        self.system_combo.setCurrentText(DEFAULT_SETTINGS["system"])
        self.thread_spin.setValue(DEFAULT_SETTINGS["max_concurrent_tasks"])

    def _apply_settings(self):
        """应用"""
        self.settings.setValue("gpu_acceleration", self.gpu_check.isChecked())
        self.settings.setValue("auto_detect", self.auto_check.isChecked())
        self.settings.setValue("ha_test", self.ha_check.isChecked())
        self.settings.setValue("system", self.system_combo.currentText())
        self.settings.setValue("max_concurrent_tasks", self.thread_spin.value())
        self.settings.sync()
        QMessageBox.information(self, "应用", "设置已应用")

    def _accept_settings(self):
        """确定"""
        self._apply_settings()
        self.accept()


# ==================== 视频转码选项对话框 ====================
class VideoTranscodeDialog(QDialog):
    """视频转码选项对话框"""
    task_created = pyqtSignal(object)  # TranscodeParams

    def __init__(self, parent=None, initial_files: List[str] = None):
        super().__init__(parent)
        self.setWindowTitle("视频转码选项")
        self.resize(500, 650)  # 稍微调高以容纳新控件

        self.input_files: List[str] = initial_files or []
        self.settings = QSettings(SETTINGS_FILE, QSettings.Format.IniFormat)

        self._setup_ui()
        self._update_file_label()
        self._load_defaults()
        # 初始化预设列表（根据默认编码器和GPU状态）
        self._update_preset_list()

    def _setup_ui(self):
        """设置UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # ---------- 创建滚动区域 ----------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 滚动区域的内容控件
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        # ===== 1. 文件拖拽区域 =====
        drop_frame = QFrame()
        drop_frame.setFrameShape(QFrame.Shape.StyledPanel)
        drop_frame.setStyleSheet("""
            QFrame {
                border: 2px dashed #888;
                border-radius: 8px;
                background-color: #f5f5f5;
                padding: 20px;
            }
            QFrame:hover {
                border-color: #0078d4;
                background-color: #e8f4fc;
            }
        """)
        drop_layout = QVBoxLayout(drop_frame)

        self.file_label = QLabel("将视频文件拖拽至此，或点击选择文件")
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label.setWordWrap(True)
        font = QFont()
        font.setPointSize(11)
        self.file_label.setFont(font)
        drop_layout.addWidget(self.file_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.open_file_btn = QPushButton("打开文件")
        self.open_file_btn.clicked.connect(self._open_file_dialog)
        btn_layout.addWidget(self.open_file_btn)
        btn_layout.addStretch()
        drop_layout.addLayout(btn_layout)

        drop_frame.setAcceptDrops(True)
        drop_frame.dragEnterEvent = self._drag_enter_event
        drop_frame.dropEvent = self._drop_event

        scroll_layout.addWidget(drop_frame)

        # ===== 2. 选项卡 =====
        tab_widget = QTabWidget()

        # --- 视频选项卡 ---
        video_tab = QWidget()
        video_layout = QFormLayout(video_tab)
        video_layout.setSpacing(10)

        # 输出格式
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MKV"])
        video_layout.addRow("输出格式:", self.format_combo)

        # 视频编码
        self.vcodec_combo = QComboBox()
        self.vcodec_combo.addItems(["HEVC (H.265)", "H.264", "VP9", "AV1", "Copy"])
        self.vcodec_combo.setCurrentText("HEVC (H.265)")
        self.vcodec_combo.currentTextChanged.connect(self._update_preset_list)
        video_layout.addRow("视频编码:", self.vcodec_combo)

        # 屏幕大小
        self.resolution_combo = QComboBox()
        self.resolution_combo.setEditable(True)
        self.resolution_combo.addItems([
            "默认（原视频尺寸）",
            "7680x4320 (8K)",
            "3840x2160 (4K)",
            "2560x1440 (2K)",
            "1920x1080 (1080p)",
            "1280x720 (720p)",
            "854x480 (480p)",
            "640x360 (360p)",
            "自定义"
        ])
        video_layout.addRow("屏幕大小:", self.resolution_combo)

        # 码率
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.setEditable(True)
        self.bitrate_combo.addItems([
            "默认（16000）",
            "50000", "30000", "20000", "16000",
            "12000", "8000", "6000", "4000", "2000", "1000"
        ])
        video_layout.addRow("码率 (kbps):", self.bitrate_combo)

        # CRF
        self.crf_combo = QComboBox()
        self.crf_combo.setEditable(True)
        self.crf_combo.addItems(["关闭", "18", "20", "23", "25", "28", "30", "35"])
        self.crf_combo.setCurrentText("关闭")
        self.crf_combo.currentTextChanged.connect(self._on_crf_changed)
        video_layout.addRow("CRF:", self.crf_combo)

        crf_tip = QLabel("提示：启用CRF时，码率设置将失效（质量优先模式）")
        crf_tip.setStyleSheet("color: gray; font-size: 10px;")
        video_layout.addRow("", crf_tip)

        # GPU
        self.gpu_check = QCheckBox("启用GPU加速")
        self.gpu_check.setToolTip("需要NVIDIA显卡支持")
        self.gpu_check.stateChanged.connect(self._update_preset_list)
        video_layout.addRow("GPU:", self.gpu_check)

        # 编码速度预设（新增）
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip("编码速度/质量权衡，越慢质量越好（压缩率越高）")
        video_layout.addRow("编码速度预设:", self.preset_combo)

        # 每秒帧数
        self.fps_combo = QComboBox()
        self.fps_combo.setEditable(True)
        self.fps_combo.addItems([
            "默认（原视频）", "120", "60", "30", "24", "20", "15"
        ])
        video_layout.addRow("每秒帧数:", self.fps_combo)

        # 宽高比
        self.aspect_combo = QComboBox()
        self.aspect_combo.setEditable(True)
        self.aspect_combo.addItems([
            "自动（原视频）", "16:9", "4:3", "1:1", "2.35:1", "2.39:1", "21:9"
        ])
        video_layout.addRow("宽高比:", self.aspect_combo)

        # 二次编码
        self.twopass_combo = QComboBox()
        self.twopass_combo.addItems(["否", "是"])
        self.twopass_combo.setToolTip("两次编码可以获得更好的质量，但耗时更长")
        video_layout.addRow("二次编码:", self.twopass_combo)

        # 关键帧间隔
        self.keyint_combo = QComboBox()
        self.keyint_combo.setEditable(True)
        self.keyint_combo.addItems(["默认", "25", "50", "100", "150", "200", "250", "300"])
        video_layout.addRow("关键帧间隔:", self.keyint_combo)

        # 旋转
        self.rotate_combo = QComboBox()
        self.rotate_combo.addItems(["否", "90°", "180°", "270°"])
        video_layout.addRow("旋转:", self.rotate_combo)

        # 左右颠倒
        self.hflip_combo = QComboBox()
        self.hflip_combo.addItems(["否", "是"])
        video_layout.addRow("左右颠倒:", self.hflip_combo)

        # 上下颠倒
        self.vflip_combo = QComboBox()
        self.vflip_combo.addItems(["否", "是"])
        video_layout.addRow("上下颠倒:", self.vflip_combo)

        tab_widget.addTab(video_tab, "视频")

        # --- 音频选项卡 ---
        audio_tab = QWidget()
        audio_layout = QFormLayout(audio_tab)
        audio_layout.setSpacing(10)

        # 音频编码
        self.acodec_combo = QComboBox()
        self.acodec_combo.addItems(["AAC", "MP3", "AC3", "FLAC", "Opus", "Copy"])
        self.acodec_combo.setCurrentText("AAC")
        audio_layout.addRow("音频编码:", self.acodec_combo)

        # 采样率
        self.ar_combo = QComboBox()
        self.ar_combo.setEditable(True)
        self.ar_combo.addItems([
            "默认（原视频）", "48000", "44100", "32000", "24000", "22050", "16000"
        ])
        audio_layout.addRow("采样率 (Hz):", self.ar_combo)

        # 比特率
        self.abitrate_combo = QComboBox()
        self.abitrate_combo.setEditable(True)
        self.abitrate_combo.addItems([
            "默认（320）", "320", "256", "192", "160", "128", "96", "64"
        ])
        audio_layout.addRow("比特率 (kbps):", self.abitrate_combo)

        # 声道
        self.channels_combo = QComboBox()
        self.channels_combo.setEditable(True)
        self.channels_combo.addItems([
            "默认（2）", "1", "2", "6", "8"
        ])
        audio_layout.addRow("声道:", self.channels_combo)

        # 音量
        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setRange(0, 999)
        self.volume_spin.setValue(100)
        self.volume_spin.setSuffix("%")
        self.volume_spin.setToolTip("0% - 999%，100%为原始音量")
        audio_layout.addRow("音量:", self.volume_spin)

        # 保留所有源输入流
        self.copy_streams_check = QCheckBox("保留所有源输入流（包括多音轨）")
        self.copy_streams_check.setChecked(True)
        audio_layout.addRow("", self.copy_streams_check)

        tab_widget.addTab(audio_tab, "音频")

        scroll_layout.addWidget(tab_widget)

        # ===== 3. 输出文件夹 =====
        output_group = QGroupBox("输出文件夹")
        output_layout = QHBoxLayout(output_group)

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setText("输出到源文件目录")
        self.output_path_edit.setReadOnly(True)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_output)

        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(self.browse_btn)

        scroll_layout.addWidget(output_group)

        # 将滚动内容设置到滚动区域
        scroll.setWidget(scroll_content)

        # 将滚动区域添加到主布局
        main_layout.addWidget(scroll)

        # ===== 4. 执行任务按钮 =====
        action_layout = QHBoxLayout()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)

        self.default_btn = QPushButton("默认")
        self.default_btn.clicked.connect(self._restore_defaults)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.setToolTip("添加到任务列表")
        self.ok_btn.clicked.connect(lambda: self._accept_task(start_now=False))

        self.ok_start_btn = QPushButton("确定并开始")
        self.ok_start_btn.setToolTip("添加到任务列表并立即开始")
        self.ok_start_btn.setDefault(True)
        self.ok_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #006cbd;
            }
        """)
        self.ok_start_btn.clicked.connect(lambda: self._accept_task(start_now=True))

        action_layout.addWidget(self.cancel_btn)
        action_layout.addWidget(self.default_btn)
        action_layout.addStretch()
        action_layout.addWidget(self.ok_btn)
        action_layout.addWidget(self.ok_start_btn)

        main_layout.addLayout(action_layout)

    def _update_preset_list(self):
        """根据当前视频编码和GPU选项更新预设下拉框的内容"""
        vcodec_text = self.vcodec_combo.currentText()
        gpu_enabled = self.gpu_check.isChecked()

        # 确定实际使用的编码器名称
        if vcodec_text == "Copy":
            # 复制流时无需预设
            self.preset_combo.clear()
            self.preset_combo.setEnabled(False)
            return

        if gpu_enabled and vcodec_text in GPU_CODEC_MAP:
            # 硬件编码（当前仅支持NVIDIA，但可扩展）
            encoder = GPU_CODEC_MAP[vcodec_text]  # 例如 hevc_nvenc
        else:
            encoder = CODEC_MAP.get(vcodec_text, "libx265")  # 软件编码

        # 根据编码器类型选择预设列表
        if encoder in ['hevc_nvenc', 'h264_nvenc']:
            presets = NVENC_PRESETS
            default = "medium"
        elif encoder in ['hevc_qsv', 'h264_qsv']:
            presets = QSV_PRESETS
            default = "medium"
        elif encoder in ['hevc_amf', 'h264_amf']:
            presets = AMF_PRESETS
            default = "balanced"
        elif encoder in ['libx264', 'libx265']:
            presets = SOFTWARE_PRESETS
            default = "medium"
        else:
            # 其他编码器（VP9、AV1等）暂不支持预设，禁用下拉框
            self.preset_combo.clear()
            self.preset_combo.setEnabled(False)
            return

        # 更新下拉框
        self.preset_combo.clear()
        self.preset_combo.addItems(presets)
        # 设置默认值（如果当前值不在列表中，则设为默认）
        current = self.preset_combo.currentText()
        if current not in presets:
            self.preset_combo.setCurrentText(default)
        self.preset_combo.setEnabled(True)

    def _drag_enter_event(self, event: QDragEnterEvent):
        """拖拽进入"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop_event(self, event: QDropEvent):
        """拖拽放下"""
        urls = event.mimeData().urls()
        files = [url.toLocalFile() for url in urls if url.toLocalFile()]
        video_files = [f for f in files if is_video_file(f)]

        if video_files:
            self.input_files = video_files
            self._update_file_label()
        else:
            QMessageBox.warning(self, "提示", "未检测到有效的视频文件")

    def _open_file_dialog(self):
        """打开文件对话框"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.mpg *.mpeg *.ts *.m2ts);;所有文件 (*.*)"
        )
        if files:
            self.input_files = files
            self._update_file_label()

    def _update_file_label(self):
        """更新文件标签"""
        if not self.input_files:
            self.file_label.setText("将视频文件拖拽至此，或点击选择文件")
        elif len(self.input_files) == 1:
            self.file_label.setText(f"已选择: {Path(self.input_files[0]).name}")
        else:
            self.file_label.setText(f"已选择 {len(self.input_files)} 个文件:\n" +
                                    "\n".join([f"  • {Path(f).name}" for f in self.input_files[:3]]) +
                                    ("\n  ..." if len(self.input_files) > 3 else ""))

    def _browse_output(self):
        """浏览输出文件夹"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if dir_path:
            self.output_path_edit.setText(dir_path)

    def _on_crf_changed(self, text: str):
        """CRF改变时禁用码率"""
        if text != "关闭":
            self.bitrate_combo.setEnabled(False)
            self.bitrate_combo.setToolTip("CRF启用时，码率设置自动失效")
        else:
            self.bitrate_combo.setEnabled(True)
            self.bitrate_combo.setToolTip("")

    def _restore_defaults(self):
        """恢复默认设置"""
        self.format_combo.setCurrentText("MP4")
        self.vcodec_combo.setCurrentText("HEVC (H.265)")
        self.resolution_combo.setCurrentText("默认（原视频尺寸）")
        self.bitrate_combo.setCurrentText("默认（16000）")
        self.crf_combo.setCurrentText("关闭")
        self._on_crf_changed("关闭")
        self.gpu_check.setChecked(False)
        # 预设会在 _update_preset_list 中自动设置为默认
        self.fps_combo.setCurrentText("默认（原视频）")
        self.aspect_combo.setCurrentText("自动（原视频）")
        self.twopass_combo.setCurrentText("否")
        self.keyint_combo.setCurrentText("默认")
        self.rotate_combo.setCurrentText("否")
        self.hflip_combo.setCurrentText("否")
        self.vflip_combo.setCurrentText("否")

        self.acodec_combo.setCurrentText("AAC")
        self.ar_combo.setCurrentText("默认（原视频）")
        self.abitrate_combo.setCurrentText("默认（320）")
        self.channels_combo.setCurrentText("默认（2）")
        self.volume_spin.setValue(100)
        self.copy_streams_check.setChecked(True)

        self.output_path_edit.setText("输出到源文件目录")

        # 更新预设列表并设置默认值
        self._update_preset_list()

    def _load_defaults(self):
        """加载默认设置（从全局设置）"""
        gpu_default = self.settings.value("gpu_acceleration", False, type=bool)
        self.gpu_check.setChecked(gpu_default)

    def _accept_task(self, start_now: bool = False):
        """确认添加任务"""
        if not self.input_files:
            QMessageBox.warning(self, "提示", "请先添加输入文件")
            return

        # 为每个文件创建任务
        for file_path in self.input_files:
            params = TranscodeParams(
                input_file=file_path,
                output_format=self.format_combo.currentText().lower(),
                video_codec=self.vcodec_combo.currentText(),
                resolution=self.resolution_combo.currentText(),
                bitrate=self.bitrate_combo.currentText(),
                crf=self.crf_combo.currentText(),
                gpu=self.gpu_check.isChecked(),
                fps=self.fps_combo.currentText(),
                aspect=self.aspect_combo.currentText(),
                twopass=self.twopass_combo.currentText(),
                keyint=self.keyint_combo.currentText(),
                rotate=self.rotate_combo.currentText(),
                hflip=self.hflip_combo.currentText(),
                vflip=self.vflip_combo.currentText(),
                audio_codec=self.acodec_combo.currentText(),
                audio_rate=self.ar_combo.currentText(),
                audio_bitrate=self.abitrate_combo.currentText(),
                audio_channels=self.channels_combo.currentText(),
                volume=self.volume_spin.value(),
                copy_streams=self.copy_streams_check.isChecked(),
                output_folder=self.output_path_edit.text(),
                preset=self.preset_combo.currentText() if self.preset_combo.isEnabled() else "medium"
            )

            self.task_created.emit(params)

        self.accept()

        # 如果要求立即开始，通知主窗口
        if start_now:
            QTimer.singleShot(100, lambda: self.parent().start_all_tasks() if hasattr(self.parent(),
                                                                                      'start_all_tasks') else None)


# ==================== 主窗口 ====================
class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频转码工具+支持AVS3+编码速度选项（测试版）")
        self.resize(1100, 700)

        # 任务管理器
        self.task_manager = TaskManager()
        self.task_manager.task_added.connect(self._on_task_added)
        self.task_manager.task_updated.connect(self._on_task_updated)
        self.task_manager.task_removed.connect(self._on_task_removed)

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()

        # 设置拖放
        self.setAcceptDrops(True)

    def _setup_ui(self):
        """设置UI"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # ===== 工具栏 =====
        toolbar = QFrame()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 5, 5, 5)

        self.add_task_btn = QPushButton("+ 新建任务")
        self.add_task_btn.setToolTip("添加新的转码任务")
        self.add_task_btn.clicked.connect(self._open_transcode_dialog)
        toolbar_layout.addWidget(self.add_task_btn)

        toolbar_layout.addStretch()

        self.settings_btn = QPushButton("⚙ 全局设置")
        self.settings_btn.setToolTip("打开全局设置")
        self.settings_btn.clicked.connect(self._open_global_settings)
        toolbar_layout.addWidget(self.settings_btn)

        layout.addWidget(toolbar)

        # ===== 任务列表 =====
        task_group = QGroupBox("任务列表")
        task_layout = QVBoxLayout(task_group)

        # 操作按钮
        btn_layout = QHBoxLayout()

        self.remove_btn = QPushButton("移除选定")
        self.remove_btn.setToolTip("移除选中的任务")
        self.remove_btn.clicked.connect(self._remove_selected_task)

        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.setToolTip("清空所有任务")
        self.clear_btn.clicked.connect(self._clear_all_tasks)

        self.stop_all_btn = QPushButton("⏹ 停止所有")
        self.stop_all_btn.setToolTip("停止所有正在进行的任务")
        self.stop_all_btn.clicked.connect(self._stop_all_tasks)

        self.start_all_btn = QPushButton("▶ 开始所有")
        self.start_all_btn.setToolTip("开始所有等待中的任务")
        self.start_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.start_all_btn.clicked.connect(self._start_all_tasks)

        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.stop_all_btn)
        btn_layout.addWidget(self.start_all_btn)

        task_layout.addLayout(btn_layout)

        # 任务表格
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(6)
        self.task_table.setHorizontalHeaderLabels([
            "文件名", "格式", "状态/进度", "输出大小", "输出路径", "操作"
        ])

        # 设置列宽
        header = self.task_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 60)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 180)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 120)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 80)

        self.task_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.task_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.setAlternatingRowColors(True)

        task_layout.addWidget(self.task_table)

        layout.addWidget(task_group, 1)

        # ===== 日志区域 =====
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: Consolas, Monaco, monospace;
                font-size: 11px;
            }
        """)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

    def _setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件")

        new_action = QAction("新建任务", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._open_transcode_dialog)
        file_menu.addAction(new_action)

        file_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 任务菜单
        task_menu = menubar.addMenu("任务")

        start_action = QAction("开始所有", self)
        start_action.setShortcut("F5")
        start_action.triggered.connect(self._start_all_tasks)
        task_menu.addAction(start_action)

        stop_action = QAction("停止所有", self)
        stop_action.setShortcut("F6")
        stop_action.triggered.connect(self._stop_all_tasks)
        task_menu.addAction(stop_action)

        task_menu.addSeparator()

        clear_action = QAction("清空列表", self)
        clear_action.triggered.connect(self._clear_all_tasks)
        task_menu.addAction(clear_action)

        # 设置菜单
        settings_menu = menubar.addMenu("设置")

        global_action = QAction("全局设置", self)
        global_action.setShortcut("Ctrl+,")
        global_action.triggered.connect(self._open_global_settings)
        settings_menu.addAction(global_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助")

        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        """设置状态栏"""
        self.status_label = QLabel("就绪")
        self.statusBar().addWidget(self.status_label)

        self.statusBar().addPermanentWidget(QLabel("|"))

        self.task_count_label = QLabel("任务: 0")
        self.statusBar().addPermanentWidget(self.task_count_label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """拖拽放下"""
        urls = event.mimeData().urls()
        files = [url.toLocalFile() for url in urls if url.toLocalFile()]
        video_files = [f for f in files if is_video_file(f)]

        if video_files:
            self._open_transcode_dialog(video_files)
        else:
            QMessageBox.warning(self, "提示", "未检测到有效的视频文件")

    def _open_global_settings(self):
        """打开全局设置"""
        dlg = GlobalSettingsDialog(self)
        dlg.exec()

    def _open_transcode_dialog(self, files: List[str] = None):
        """打开转码选项对话框"""
        dlg = VideoTranscodeDialog(self, files)
        dlg.task_created.connect(self.task_manager.add_task)
        dlg.exec()

    def _start_all_tasks(self):
        """开始所有任务"""
        self.task_manager.start_all_pending()
        self._log("开始执行所有等待中的任务")

    def start_all_tasks(self):
        """供外部调用的开始所有任务"""
        self._start_all_tasks()

    def _stop_all_tasks(self):
        """停止所有任务"""
        self.task_manager.stop_all_tasks()
        self._log("已停止所有任务")

    def _clear_all_tasks(self):
        """清空所有任务"""
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.task_manager.clear_all_tasks()
            self.task_table.setRowCount(0)
            self._update_task_count()
            self._log("已清空任务列表")

    def _remove_selected_task(self):
        """移除选中的任务"""
        current_row = self.task_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "提示", "请先选择要移除的任务")
            return

        item = self.task_table.item(current_row, 0)
        if item:
            task_id = item.data(Qt.ItemDataRole.UserRole)
            self.task_manager.remove_task(task_id)

    def _on_task_added(self, task: TaskInfo):
        """任务添加回调"""
        row = self.task_table.rowCount()
        self.task_table.insertRow(row)

        # 文件名
        file_name = Path(task.params.input_file).name
        name_item = QTableWidgetItem(file_name)
        name_item.setData(Qt.ItemDataRole.UserRole, task.id)
        name_item.setToolTip(task.params.input_file)
        self.task_table.setItem(row, 0, name_item)

        # 格式
        fmt = task.params.output_format.upper()
        self.task_table.setItem(row, 1, QTableWidgetItem(fmt))

        # 状态/进度
        status_widget = self._create_status_widget(task.status, task.progress)
        self.task_table.setCellWidget(row, 2, status_widget)

        # 输出大小
        self.task_table.setItem(row, 3, QTableWidgetItem("-"))

        # 输出路径
        self.task_table.setItem(row, 4, QTableWidgetItem("-"))

        # 操作按钮
        del_btn = QPushButton("删除")
        del_btn.setStyleSheet("padding: 2px 8px;")
        del_btn.clicked.connect(lambda: self.task_manager.remove_task(task.id))
        self.task_table.setCellWidget(row, 5, del_btn)

        self._update_task_count()
        self._log(f"添加任务: {file_name}")

    def _on_task_updated(self, update: dict):
        """任务更新回调"""
        task_id = update.get("id") or update.get("task_id")
        if not task_id:
            return

        # 查找对应行
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                # 更新状态/进度
                if "status" in update or "progress" in update:
                    status = update.get("status", "")
                    progress = update.get("progress", 0)
                    status_widget = self._create_status_widget(status, progress)
                    self.task_table.setCellWidget(row, 2, status_widget)

                # 更新输出大小和路径
                if "output_file" in update:
                    out_file = update.get("output_file")
                    out_size = update.get("output_size", 0)
                    percent = update.get("percent_change", 0.0)

                    # 大小显示（带箭头）
                    size_text = format_size(out_size) + "  " + percent_arrow(percent)
                    size_item = QTableWidgetItem(size_text)
                    if percent > 0:
                        size_item.setForeground(Qt.GlobalColor.red)
                    elif percent < 0:
                        size_item.setForeground(Qt.GlobalColor.darkGreen)
                    self.task_table.setItem(row, 3, size_item)

                    # 可点击的路径
                    if out_file:
                        link_label = QLabel()
                        link_label.setText(f'<a href="file:///{out_file}">{Path(out_file).name}</a>')
                        link_label.setOpenExternalLinks(True)
                        link_label.setToolTip(out_file)
                        link_label.setStyleSheet("color: #0078d4;")
                        self.task_table.setCellWidget(row, 4, link_label)

                        self._log(f"任务完成: {Path(out_file).name} ({size_text})")

                # 错误信息
                if "error" in update:
                    error_msg = update.get("error", "")
                    self._log(f"任务错误: {error_msg[:100]}")

                break

    def _on_task_removed(self, task_id: int):
        """任务移除回调"""
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                self.task_table.removeRow(row)
                break
        self._update_task_count()

    def _create_status_widget(self, status: str, progress: int) -> QWidget:
        """创建状态显示组件（支持忙碌动画）"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(8)

        # 状态标签
        status_label = QLabel(status)
        status_label.setFixedWidth(60)

        # 根据状态设置颜色
        if status == "完成":
            status_label.setStyleSheet("color: green; font-weight: bold;")
        elif status == "错误":
            status_label.setStyleSheet("color: red; font-weight: bold;")
        elif status == "转码中":
            status_label.setStyleSheet("color: blue;")
        elif status == "等待中":
            status_label.setStyleSheet("color: gray;")

        # 进度条
        progress_bar = QProgressBar()
        if status == "转码中" and progress == 0:
            # 未知进度时显示忙碌动画
            progress_bar.setRange(0, 0)
        else:
            progress_bar.setRange(0, 100)
            progress_bar.setValue(progress)
            progress_bar.setTextVisible(True)
            progress_bar.setFormat("%p%")
        progress_bar.setFixedWidth(80)

        layout.addWidget(status_label)
        layout.addWidget(progress_bar)
        layout.addStretch()

        return widget

    def _update_task_count(self):
        """更新任务计数"""
        count = self.task_table.rowCount()
        self.task_count_label.setText(f"任务: {count}")

    def _log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 视频转码工具",
            """<h2>视频转码工具 1.5</h2>
            <p>徐某的视频转码软件 (2026年2月26日)</p>
            <p>基于 Python + PyQt6 + FFmpeg</p>
            <p>支持 GPU 加速、批量转码、多线程处理、编码速度预设（测试版）</p>
            <p>集成 AVS3 解码支持，就为了转码8K春晚！</p>
            <hr>
            <pre>在还有没完成的任务时，其余显示99%的就是已经好了的。</pre>
            <pre>还有什么bug可以自己测一下，懒得修复了。</pre>
            """
        )

    def closeEvent(self, event):
        """关闭事件"""
        # 停止所有任务
        self.task_manager.stop_all_tasks()
        # 等待线程池完成
        self.task_manager._thread_pool.waitForDone(3000)
        event.accept()


# ==================== 程序入口 ====================
def main():
    """主函数"""
    # 高DPI支持
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    # 设置FFmpeg环境（必须在QApplication之前，因为可能用到环境变量）
    setup_ffmpeg_environment()

    app = QApplication(sys.argv)
    app.setApplicationName("视频转码工具+支持AVS3+编码速度预设（测试版）")
    app.setOrganizationName("VideoTranscoder+AVS3")

    # 设置应用样式
    app.setStyle('Fusion')

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
