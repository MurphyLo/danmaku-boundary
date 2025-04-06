import cv2
import os
import time
from datetime import timedelta
from PyQt5.QtWidgets import (QLabel, QMessageBox, QPushButton, QSlider, 
                           QFileDialog, QStyle)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QTimer, QEvent
from ui_components import ClickableSlider

class VideoPlayer:
    def __init__(self, parent):
        self.parent = parent
        
        # 视频属性
        self.video_path = None
        self.cap = None
        self.frame_count = 0
        self.fps = 0
        self.current_frame = 0
        self.playing = False
        self._was_playing = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.video_width = 0
        self.video_height = 0
        
        # UI 元素引用
        self.video_label = None
        self.time_label = None
        self.slider = None
        self.play_btn = None
        
        # 控制标志
        self.need_jump = True  # 是否需要跳转（随机访问视频帧）
        self.is_dragging = False  # 是否正在拖动进度条
        
        # 帧更新节流控制变量
        self.last_update_time = 0  # 上次更新帧的时间
        self.throttle_interval = 80  # 节流间隔（毫秒）
    
    def setup_ui_connections(self, video_label, time_label, slider, play_btn):
        """设置UI元素的引用和事件连接"""
        self.video_label = video_label
        self.time_label = time_label
        self.slider = slider
        self.play_btn = play_btn
        
        # 连接信号
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)
        self.slider.valueChanged.connect(self.scrub_video)
        self.play_btn.clicked.connect(self.toggle_play)
    
    def open_video(self, file_path=None):
        """打开视频文件"""
        if file_path is None:
            file_path, _ = QFileDialog.getOpenFileName(self.parent, "打开视频", "", 
                                                    "视频文件 (*.mp4 *.avi *.mkv *.mov)")
        
        if not file_path:
            return False
        
        # 关闭之前打开的视频
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        
        try:
            self.cap = cv2.VideoCapture(file_path)
            
            if not self.cap.isOpened():
                raise IOError(f"无法打开视频文件: {file_path}")
            
            # 获取视频属性
            self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.video_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.video_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            if self.frame_count <= 0 or self.fps <= 0:
                raise ValueError("检测到无效的视频属性")
            
            self.current_frame = 0
            self.video_path = file_path
            
            # 设置滑块范围
            self.slider.setMaximum(self.frame_count - 1)
            self.slider.setValue(0)
            
            # 更新显示
            self.update_frame()
            
            return True
            
        except Exception as e:
            QMessageBox.critical(self.parent, "错误", f"打开视频失败: {str(e)}")
            self.cap = None
            return False
    
    def update_frame(self):
        """更新当前帧显示"""
        if self.cap is None:
            return
        
        try:
            # 如果当前帧超出范围，设置为最后一帧
            if self.current_frame >= self.frame_count:
                self.current_frame = self.frame_count - 1
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
                self.playing = False
                self.play_btn.setText("播放")
                self.timer.stop()
            
            if self.need_jump:
                # 只有在需要跳转时才调用 cap.set
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
                self.need_jump = False
            
            # 读取当前帧
            ret, frame = self.cap.read()
            
            if not ret:
                # 读取失败，可能是到达了视频末尾
                self.timer.stop()
                self.playing = False
                self.play_btn.setText("播放")
                # 设置为最后一帧
                self.current_frame = self.frame_count - 1
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
                ret, frame = self.cap.read()
                if not ret:
                    # 如果仍然无法读取，说明视频文件可能有问题
                    return
            
            # 转换颜色空间并显示
            self.display_frame(frame)
            
            # 更新时间标签
            current_time = self.frame_to_time(self.current_frame)
            total_time = self.frame_to_time(self.frame_count)
            self.time_label.setText(f"{current_time} / {total_time}")
            
            # 更新滑块位置（不触发valueChanged信号）
            self.slider.blockSignals(True)
            self.slider.setValue(self.current_frame)
            self.slider.blockSignals(False)
            
            # 如果处于播放状态，播放下一帧
            if self.playing and not self.is_dragging:
                self.current_frame += 1
                
                # 如果到达视频结尾，停止播放
                if self.current_frame >= self.frame_count:
                    self.toggle_play()
            
        except Exception as e:
            self.timer.stop()
            self.playing = False
            self.play_btn.setText("播放")
            QMessageBox.critical(self.parent, "错误", f"显示帧时出错: {str(e)}")
    
    def display_frame(self, frame):
        """将OpenCV格式的帧转换为Qt格式并显示"""
        # 转换颜色空间
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 转换为QImage
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        # 调整大小以适应标签
        pixmap = QPixmap.fromImage(q_img)
        
        # 计算适当的大小来保持纵横比
        label_size = self.video_label.size()
        scaled_pixmap = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # 显示帧
        self.video_label.setPixmap(scaled_pixmap)
    
    def frame_to_time(self, frame_number):
        """将帧数转换为时间字符串"""
        if self.fps <= 0:
            return "00:00:00"
        
        seconds = frame_number / self.fps
        time_obj = timedelta(seconds=seconds)
        return str(time_obj).split('.')[0]  # 去掉毫秒部分
    
    def time_to_frame(self, time_str):
        """将时间字符串转换为帧数"""
        try:
            h, m, s = map(int, time_str.split(':'))
            total_seconds = h * 3600 + m * 60 + s
            return int(total_seconds * self.fps)
        except:
            return 0
    
    def toggle_play(self):
        """切换播放/暂停状态"""
        if self.cap is None:
            return
        
        self.playing = not self.playing
        
        if self.playing:
            self.play_btn.setText("暂停")
            self.timer.start(int(1000 / (self.fps)))  # 帧率的两倍来确保流畅播放
        else:
            self.play_btn.setText("播放")
            self.timer.stop()
    
    def slider_pressed(self):
        """按下滑块时暂停视频"""
        if self.playing:
            self.toggle_play()
            self._was_playing = True
        else:
            self._was_playing = False

        self.is_dragging = True
        # 重置节流时间，确保拖动开始时立即显示第一帧
        self.last_update_time = 0
    
    def slider_released(self):
        """释放滑块后跳转到相应位置"""
        self.current_frame = self.slider.value()
        self.is_dragging = False
        self.need_jump = True
        self.update_frame()
        # 重置上次更新时间
        self.last_update_time = time.time() * 1000
        
        # 如果之前是播放状态，则恢复播放
        if self._was_playing:
            self.toggle_play()
        # 重置状态，防止残留
        self._was_playing = False

    def scrub_video(self, value):
        """鼠标拖拽滑块时，实时更新画面"""
        if self.cap is None:
            return

        # 将当前拖拽位置映射到帧数
        self.current_frame = value
        
        # 如果正在拖动，进行实时预览
        if self.is_dragging:
            self.need_jump = True
            
            # 添加节流控制
            current_time = time.time() * 1000
            time_elapsed = current_time - self.last_update_time
            
            # 节流：只有经过足够的时间间隔或开始/结束拖动时才更新
            if time_elapsed >= self.throttle_interval:
                self.update_frame()
                self.last_update_time = current_time
    
    def seek_relative(self, seconds):
        """相对跳转（秒）"""
        if self.cap is None:
            return
        
        target_frame = self.current_frame + int(seconds * self.fps)
        target_frame = max(0, min(target_frame, self.frame_count - 1))
        self.current_frame = target_frame
        self.need_jump = True
        self.update_frame()
    
    def seek_frames(self, frames):
        """相对跳转（帧）"""
        if self.cap is None:
            return
        
        target_frame = self.current_frame + frames
        target_frame = max(0, min(target_frame, self.frame_count - 1))
        self.current_frame = target_frame
        self.need_jump = True
        self.update_frame()
    
    def seek_to_frame(self, frame):
        """跳转到指定帧"""
        if self.cap is None:
            return
        
        target_frame = max(0, min(frame, self.frame_count - 1))
        self.current_frame = target_frame
        self.need_jump = True
        self.update_frame()
    
    def close(self):
        """关闭视频并释放资源"""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            return True
        return False 