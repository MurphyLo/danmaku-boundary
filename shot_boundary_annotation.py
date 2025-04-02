import os
import sys
import cv2
import json
import time
import datetime
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QSlider, QLabel, 
                            QFileDialog, QShortcut, QMessageBox)
from PyQt5.QtGui import QImage, QPixmap, QKeySequence
from PyQt5.QtCore import Qt, QTimer, QUrl, QSize
from PyQt5.QtWidgets import QStyle

class ShotBoundaryAnnotator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("镜头边界标注工具")
        self.setGeometry(100, 100, 1200, 800)
        
        # 视频相关变量
        self.video_path = ""
        self.cap = None
        self.fps = 0
        self.total_frames = 0
        self.current_frame = 0
        self.is_playing = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        
        # 缓存相关
        self.frame_cache = {}  # 用于缓存最近使用的帧
        self.cache_size = 30   # 缓存的帧数量
        self.last_render_time = 0.0  # 上次渲染时间，修改为浮点数
        self.render_interval = 33  # 约30 FPS的渲染速率 (毫秒)
        
        # 标注相关变量
        self.annotations = []
        self.temp_annotation = None  # 用于存储渐变标注的开始时间
        self.annotation_mode = "cut"  # 默认为直接切换模式 "cut" 或 "transition"
        
        # 初始化UI
        self.init_ui()
        
        # 设置键盘快捷键
        self.setup_shortcuts()
    
    def init_ui(self):
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 视频显示区域
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(800, 450)
        self.video_label.setStyleSheet("background-color: black;")
        main_layout.addWidget(self.video_label)
        
        # 进度条
        slider_layout = QHBoxLayout()
        self.time_label = QLabel("00:00:00 / 00:00:00")
        
        # 自定义进度条，添加点击支持
        class ClickableSlider(QSlider):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.parent_annotator = None  # 添加对父对象的引用
            
            def set_parent_annotator(self, annotator):
                self.parent_annotator = annotator
            
            def mousePressEvent(self, event):
                # 覆盖鼠标点击事件，实现点击定位功能
                if event.button() == Qt.LeftButton:
                    value = QStyle.sliderValueFromPosition(
                        self.minimum(), self.maximum(), 
                        event.x(), self.width()
                    )
                    self.setValue(value)
                    self.sliderMoved.emit(value)
                    # 不再直接发射sliderReleased信号，而是模拟正常拖动后的释放
                super().mousePressEvent(event)
            
            def mouseReleaseEvent(self, event):
                if event.button() == Qt.LeftButton and self.parent_annotator:
                    # 点击释放时直接调用父对象的slider_released方法，保持一致行为
                    self.parent_annotator.slider_released()
                super().mouseReleaseEvent(event)
        
        # 使用可点击的进度条
        self.progress_slider = ClickableSlider(Qt.Horizontal)
        self.progress_slider.set_parent_annotator(self)  # 设置父对象引用
        self.progress_slider.setEnabled(True)
        self.progress_slider.setFocusPolicy(Qt.StrongFocus)
        self.progress_slider.setPageStep(10)  # 设置页面步长
        self.progress_slider.setSingleStep(1)  # 设置单步长度
        self.progress_slider.setTracking(True)  # 启用跟踪，这样拖动时会更新
        self.progress_slider.sliderMoved.connect(self.slider_moved)
        self.progress_slider.sliderReleased.connect(self.slider_released)
        slider_layout.addWidget(self.time_label)
        slider_layout.addWidget(self.progress_slider)
        main_layout.addLayout(slider_layout)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        
        self.open_btn = QPushButton("打开视频")
        self.open_btn.clicked.connect(self.open_video)
        
        self.play_btn = QPushButton("播放")
        self.play_btn.clicked.connect(self.toggle_play)
        
        self.mode_btn = QPushButton("模式: 直接切换")
        self.mode_btn.clicked.connect(self.toggle_mode)
        
        self.cut_btn = QPushButton("标注切换点 (Ctrl+1)")
        self.cut_btn.clicked.connect(self.annotate_cut)
        
        self.transition_start_btn = QPushButton("标注过渡开始 (Ctrl+2)")
        self.transition_start_btn.clicked.connect(self.annotate_transition_start)
        
        self.transition_end_btn = QPushButton("标注过渡结束 (Ctrl+3)")
        self.transition_end_btn.clicked.connect(self.annotate_transition_end)
        
        self.save_btn = QPushButton("保存标注")
        self.save_btn.clicked.connect(self.save_annotations)
        
        control_layout.addWidget(self.open_btn)
        control_layout.addWidget(self.play_btn)
        control_layout.addWidget(self.mode_btn)
        control_layout.addWidget(self.cut_btn)
        control_layout.addWidget(self.transition_start_btn)
        control_layout.addWidget(self.transition_end_btn)
        control_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(control_layout)
        
        # 标注信息区域
        self.annotation_label = QLabel("标注信息")
        self.annotation_label.setAlignment(Qt.AlignTop)
        self.annotation_label.setStyleSheet("background-color: white; border: 1px solid gray;")
        self.annotation_label.setMinimumHeight(150)
        main_layout.addWidget(self.annotation_label)
        
        # 添加CPU使用率显示
        self.status_bar = self.statusBar()
        self.cpu_label = QLabel("CPU: 降低渲染频率以减少CPU占用")
        self.status_bar.addPermanentWidget(self.cpu_label)
    
    def setup_shortcuts(self):
        # 播放控制快捷键
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_space.activated.connect(self.toggle_play)
        
        # 视频导航快捷键
        self.shortcut_right = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_right.activated.connect(lambda: self.navigate_video(5))
        
        self.shortcut_left = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_left.activated.connect(lambda: self.navigate_video(-5))
        
        self.shortcut_alt_right = QShortcut(QKeySequence("Alt+Right"), self)
        self.shortcut_alt_right.activated.connect(lambda: self.navigate_video(1))
        
        self.shortcut_alt_left = QShortcut(QKeySequence("Alt+Left"), self)
        self.shortcut_alt_left.activated.connect(lambda: self.navigate_video(-1))
        
        self.shortcut_shift_right = QShortcut(QKeySequence("Shift+Right"), self)
        self.shortcut_shift_right.activated.connect(lambda: self.navigate_frames(5))
        
        self.shortcut_shift_left = QShortcut(QKeySequence("Shift+Left"), self)
        self.shortcut_shift_left.activated.connect(lambda: self.navigate_frames(-5))
        
        # 标注快捷键
        self.shortcut_ctrl_1 = QShortcut(QKeySequence("Ctrl+1"), self)
        self.shortcut_ctrl_1.activated.connect(self.annotate_cut)
        
        self.shortcut_ctrl_2 = QShortcut(QKeySequence("Ctrl+2"), self)
        self.shortcut_ctrl_2.activated.connect(self.annotate_transition_start)
        
        self.shortcut_ctrl_3 = QShortcut(QKeySequence("Ctrl+3"), self)
        self.shortcut_ctrl_3.activated.connect(self.annotate_transition_end)
    
    def open_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "打开视频文件", "", 
                                                "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv)")
        if file_path:
            self.video_path = file_path
            self.load_video()
    
    def load_video(self):
        # 如果之前已加载视频，先释放资源
        if self.cap is not None:
            self.cap.release()
        
        # 清空帧缓存
        self.frame_cache = {}
        
        # 加载新视频
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            QMessageBox.critical(self, "错误", "无法打开视频文件")
            return
        
        # 获取视频信息
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_frame = 0
        
        # 调整定时器间隔，低帧率视频使用更长的间隔
        # 但不低于30 FPS的播放速率，以保持流畅度
        playback_interval = max(33, int(1000 / self.fps))
        
        # 设置滑块范围
        self.progress_slider.setMinimum(0)
        self.progress_slider.setMaximum(self.total_frames - 1)
        self.progress_slider.setValue(0)
        
        # 更新UI
        self.update_frame()
        self.setWindowTitle(f"镜头边界标注工具 - {os.path.basename(self.video_path)}")
        
        # 重置标注
        self.annotations = []
        self.temp_annotation = None
        self.update_annotation_display()
    
    def toggle_play(self):
        if not self.cap:
            return
        
        if self.is_playing:
            self.timer.stop()
            self.is_playing = False
            self.play_btn.setText("播放（Space）")
        else:
            # 使用更低的帧率更新UI，减少CPU占用
            interval = max(50, int(1000 / min(self.fps, 20)))  # 最高20 FPS的更新率
            self.timer.start(interval)
            self.is_playing = True
            self.play_btn.setText("暂停")
    
    def get_frame(self, frame_number):
        """从缓存获取帧，如果不存在则从视频读取并缓存"""
        if frame_number in self.frame_cache:
            return self.frame_cache[frame_number]
        
        # 设置当前帧位置
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = self.cap.read()
        
        if ret:
            # 缓存帧
            self.frame_cache[frame_number] = frame
            
            # 如果缓存过大，删除最旧的帧
            if len(self.frame_cache) > self.cache_size:
                oldest_frame = min(self.frame_cache.keys())
                del self.frame_cache[oldest_frame]
            
            return frame
        return None
    
    def update_frame(self):
        if not self.cap:
            return
        
        # 检查是否到达视频末尾
        if self.current_frame >= self.total_frames:
            self.timer.stop()
            self.is_playing = False
            self.play_btn.setText("播放")
            return
        
        # 获取当前时间，检查是否需要渲染
        current_time = time.time() * 1000  # 这返回一个浮点数
        should_render = (current_time - self.last_render_time) >= self.render_interval
        
        # 从缓存或文件获取当前帧
        frame = self.get_frame(self.current_frame)
        
        if frame is not None and should_render:
            # 转换帧为QImage并显示
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            
            # 计算缩放以适应label大小
            label_size = self.video_label.size()
            pixmap = QPixmap.fromImage(q_img)
            
            # 只有当label尺寸发生变化时才重新缩放图像
            if label_size.width() > 0 and label_size.height() > 0:
                scaled_pixmap = pixmap.scaled(
                    label_size, 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation if not self.is_playing else Qt.FastTransformation
                )
                self.video_label.setPixmap(scaled_pixmap)
            
            # 更新进度条
            self.progress_slider.setValue(self.current_frame)
            
            # 更新时间标签 (不需要每帧都更新，降低频率)
            if self.current_frame % 5 == 0 or not self.is_playing:
                current_time_str = self.frame_to_time_str(self.current_frame)
                total_time = self.frame_to_time_str(self.total_frames)
                self.time_label.setText(f"{current_time_str} / {total_time}")
            
            # 记录本次渲染时间
            self.last_render_time = current_time
        
        # 如果正在播放，则准备下一帧
        if self.is_playing:
            self.current_frame += 1
    
    def frame_to_time_str(self, frame_number):
        seconds = frame_number / self.fps
        return str(datetime.timedelta(seconds=seconds)).split(".")[0]
    
    def slider_moved(self, position):
        # 更新时间显示，但不跳转（等到释放后再跳转）
        current_time = self.frame_to_time_str(position)
        total_time = self.frame_to_time_str(self.total_frames)
        self.time_label.setText(f"{current_time} / {total_time}")
    
    def slider_released(self):
        # 当滑块释放时，跳转到新位置
        new_frame = self.progress_slider.value()
        if new_frame != self.current_frame:
            # 只有当位置确实变化时才进行处理
            was_playing = self.is_playing  # 记录当前播放状态
            
            # 如果正在播放，暂时停止计时器
            if self.is_playing:
                self.timer.stop()
            
            # 设置新的帧位置
            self.current_frame = new_frame
            
            # 清空帧缓存，以节省内存
            self.frame_cache = {}
            
            # 更新显示
            self.update_frame()
            
            # 如果之前是播放状态，则恢复播放
            if was_playing:
                interval = max(50, int(1000 / min(self.fps, 20)))  # 最高20 FPS的更新率
                self.timer.start(interval)
                self.is_playing = True
                self.play_btn.setText("暂停")
    
    def navigate_video(self, seconds):
        if not self.cap:
            return
        
        # 计算要跳转的帧数
        frame_shift = int(seconds * self.fps)
        new_frame = max(0, min(self.current_frame + frame_shift, self.total_frames - 1))
        
        # 清空帧缓存，以避免过多内存使用
        if abs(new_frame - self.current_frame) > self.cache_size:
            self.frame_cache = {}
            
        self.current_frame = new_frame
        self.update_frame()
    
    def navigate_frames(self, frames):
        if not self.cap:
            return
        
        # 直接按帧数进行跳转
        new_frame = max(0, min(self.current_frame + frames, self.total_frames - 1))
        self.current_frame = new_frame
        self.update_frame()
    
    def toggle_mode(self):
        if self.annotation_mode == "cut":
            self.annotation_mode = "transition"
            self.mode_btn.setText("模式: 过渡标注")
        else:
            self.annotation_mode = "cut"
            self.mode_btn.setText("模式: 直接切换")
    
    def annotate_cut(self):
        if not self.cap:
            return
        
        # 创建切换点标注
        timestamp = self.current_frame / self.fps
        time_str = self.frame_to_time_str(self.current_frame)
        
        annotation = {
            "type": "cut",
            "frame": self.current_frame,
            "timestamp": timestamp,
            "time_str": time_str
        }
        
        self.annotations.append(annotation)
        self.update_annotation_display()
    
    def annotate_transition_start(self):
        if not self.cap:
            return
        
        # 创建过渡开始标注
        timestamp = self.current_frame / self.fps
        time_str = self.frame_to_time_str(self.current_frame)
        
        # 存储临时标注
        self.temp_annotation = {
            "type": "transition_start",
            "frame": self.current_frame,
            "timestamp": timestamp,
            "time_str": time_str
        }
        
        self.update_annotation_display()
    
    def annotate_transition_end(self):
        if not self.cap or not self.temp_annotation:
            if not self.temp_annotation:
                QMessageBox.warning(self, "警告", "请先标注过渡开始点")
            return
        
        # 获取结束时间
        end_timestamp = self.current_frame / self.fps
        end_time_str = self.frame_to_time_str(self.current_frame)
        
        # 创建完整的过渡标注
        annotation = {
            "type": "transition",
            "start_frame": self.temp_annotation["frame"],
            "end_frame": self.current_frame,
            "start_timestamp": self.temp_annotation["timestamp"],
            "end_timestamp": end_timestamp,
            "start_time_str": self.temp_annotation["time_str"],
            "end_time_str": end_time_str,
            "duration": end_timestamp - self.temp_annotation["timestamp"]
        }
        
        self.annotations.append(annotation)
        self.temp_annotation = None
        self.update_annotation_display()
    
    def update_annotation_display(self):
        # 更新标注信息显示
        if not self.annotations and not self.temp_annotation:
            self.annotation_label.setText("暂无标注信息")
            return
        
        text = "标注信息:\n"
        
        # 显示临时标注（如果有）
        if self.temp_annotation:
            text += f"临时: 过渡开始于 {self.temp_annotation['time_str']} (等待标注结束点)\n"
        
        # 显示已完成的标注（最近的5个）
        if self.annotations:
            count = min(5, len(self.annotations))
            text += "\n最近的标注:\n"
            for i in range(count):
                idx = len(self.annotations) - 1 - i
                if idx < 0:
                    break
                    
                anno = self.annotations[idx]
                if anno["type"] == "cut":
                    text += f"{idx+1}. 切换点: {anno['time_str']}\n"
                elif anno["type"] == "transition":
                    text += f"{idx+1}. 过渡: {anno['start_time_str']} -> {anno['end_time_str']} (持续{anno['duration']:.2f}秒)\n"
        
        self.annotation_label.setText(text)
    
    def save_annotations(self):
        if not self.video_path or not self.annotations:
            QMessageBox.warning(self, "警告", "没有视频或标注可保存")
            return
        
        # 弹出保存文件对话框
        default_name = os.path.splitext(os.path.basename(self.video_path))[0] + "_annotations.json"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存标注", default_name, "JSON Files (*.json)")
        
        if not file_path:
            return
        
        # 创建完整的标注数据
        data = {
            "video_file": self.video_path,
            "fps": self.fps,
            "total_frames": self.total_frames,
            "annotations": self.annotations,
            "timestamp": time.time(),
            "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 将标注保存到JSON文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "成功", f"标注已保存到 {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存标注时出错: {str(e)}")
    
    def closeEvent(self, event):
        # 释放资源
        if self.cap is not None:
            self.cap.release()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = ShotBoundaryAnnotator()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 