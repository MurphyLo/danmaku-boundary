#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import cv2
import json
import time
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QListWidget, QSlider, 
                             QShortcut, QMessageBox, QFrame, QSplitter, QAction)
from PyQt5.QtGui import QImage, QPixmap, QKeySequence
from PyQt5.QtCore import Qt, QTimer, QSize

class VideoPlayerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        
    def init_ui(self):
        # 创建布局
        self.layout = QVBoxLayout(self)
        
        # 视频显示区域
        self.video_frame = QLabel()
        self.video_frame.setAlignment(Qt.AlignCenter)
        self.video_frame.setMinimumSize(640, 360)
        self.video_frame.setStyleSheet("background-color: black;")
        
        # 控制按钮区域
        control_layout = QHBoxLayout()
        
        # 播放/暂停按钮
        self.play_button = QPushButton("播放")
        self.play_button.clicked.connect(self.toggle_play)
        
        # 时间标签
        self.time_label = QLabel("00:00:00 / 00:00:00")
        
        # 进度条
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setMinimum(0)
        self.progress_slider.sliderPressed.connect(self.slider_pressed)
        self.progress_slider.sliderReleased.connect(self.slider_released)
        
        # 添加控件到控制布局
        control_layout.addWidget(self.play_button)
        control_layout.addWidget(self.time_label)
        control_layout.addWidget(self.progress_slider)
        
        # 将所有组件添加到主布局
        self.layout.addWidget(self.video_frame)
        self.layout.addLayout(control_layout)
        
        self.setLayout(self.layout)
    
    def toggle_play(self):
        if self.parent.playing:
            self.parent.pause_video()
        else:
            self.parent.play_video()
    
    def slider_pressed(self):
        self.parent.was_playing = self.parent.playing
        self.parent.pause_video()
    
    def slider_released(self):
        frame_pos = self.progress_slider.value()
        self.parent.set_position(frame_pos)
        if self.parent.was_playing:
            self.parent.play_video()


class AnnotationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        
    def init_ui(self):
        # 创建布局
        self.layout = QVBoxLayout(self)
        
        # 标注列表
        self.annotation_list = QListWidget()
        self.annotation_list.setAlternatingRowColors(True)
        
        # 标注按钮区域
        button_layout = QHBoxLayout()
        
        # 添加单次切换按钮
        self.cut_button = QPushButton("切换 (Ctrl+1)")
        self.cut_button.clicked.connect(lambda: self.parent.add_annotation(annotation_type="cut"))
        
        # 添加渐变开始按钮
        self.fade_start_button = QPushButton("渐变开始 (Ctrl+2)")
        self.fade_start_button.clicked.connect(lambda: self.parent.add_annotation(annotation_type="fade_start"))
        
        # 添加渐变结束按钮
        self.fade_end_button = QPushButton("渐变结束 (Ctrl+3)")
        self.fade_end_button.clicked.connect(lambda: self.parent.add_annotation(annotation_type="fade_end"))
        
        # 删除标注按钮
        self.delete_button = QPushButton("删除标注")
        self.delete_button.clicked.connect(self.parent.delete_selected_annotation)
        
        # 保存标注按钮
        self.save_button = QPushButton("保存标注")
        self.save_button.clicked.connect(self.parent.save_annotations)
        
        # 添加按钮到布局
        button_layout.addWidget(self.cut_button)
        button_layout.addWidget(self.fade_start_button)
        button_layout.addWidget(self.fade_end_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.save_button)
        
        # 将组件添加到主布局
        self.layout.addWidget(self.annotation_list)
        self.layout.addLayout(button_layout)
        
        self.setLayout(self.layout)


class VideoAnnotatorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_variables()
        self.init_ui()
        self.setup_shortcuts()
        
    def init_variables(self):
        self.video_path = None
        self.cap = None
        self.frame_count = 0
        self.fps = 0
        self.duration = 0
        self.current_frame = 0
        self.playing = False
        self.was_playing = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.annotations = []
        self.fade_pairs = {}  # 跟踪渐变配对
        
    def init_ui(self):
        # 设置窗口属性
        self.setWindowTitle("视频标注工具 - Camera Shot Boundary Detection")
        self.setMinimumSize(1000, 600)
        
        # 创建中央窗口部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建主布局
        main_layout = QHBoxLayout(self.central_widget)
        
        # 创建分割器，允许调整各部分大小
        splitter = QSplitter(Qt.Horizontal)
        
        # 创建视频播放器和标注工具部件
        self.video_player = VideoPlayerWidget(self)
        self.annotation_widget = AnnotationWidget(self)
        
        # 添加部件到分割器
        splitter.addWidget(self.video_player)
        splitter.addWidget(self.annotation_widget)
        
        # 设置各部分的初始大小比例
        splitter.setSizes([700, 300])
        
        # 添加分割器到主布局
        main_layout.addWidget(splitter)
        
        # 创建菜单栏
        menubar = self.menuBar()
        file_menu = menubar.addMenu('文件')
        
        # 添加打开视频动作
        open_action = QAction('打开视频', self)
        open_action.triggered.connect(self.open_video)
        file_menu.addAction(open_action)
        
        # 添加退出动作
        exit_action = QAction('退出', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 状态栏
        self.statusBar().showMessage('就绪')
        
        # 显示窗口
        self.show()
    
    def setup_shortcuts(self):
        # 播放/暂停 - 空格键
        self.shortcut_play = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_play.activated.connect(self.toggle_play)
        
        # 前进/后退5秒 - 右/左箭头
        self.shortcut_forward = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_forward.activated.connect(lambda: self.seek_relative(seconds=5))
        
        self.shortcut_backward = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_backward.activated.connect(lambda: self.seek_relative(seconds=-5))
        
        # 前进/后退1秒 - Alt+右/左箭头
        self.shortcut_forward_1s = QShortcut(QKeySequence("Alt+Right"), self)
        self.shortcut_forward_1s.activated.connect(lambda: self.seek_relative(seconds=1))
        
        self.shortcut_backward_1s = QShortcut(QKeySequence("Alt+Left"), self)
        self.shortcut_backward_1s.activated.connect(lambda: self.seek_relative(seconds=-1))
        
        # 前进/后退5帧 - Shift+右/左箭头
        self.shortcut_forward_5f = QShortcut(QKeySequence("Shift+Right"), self)
        self.shortcut_forward_5f.activated.connect(lambda: self.seek_relative(frames=5))
        
        self.shortcut_backward_5f = QShortcut(QKeySequence("Shift+Left"), self)
        self.shortcut_backward_5f.activated.connect(lambda: self.seek_relative(frames=-5))
        
        # 标注快捷键
        self.shortcut_cut = QShortcut(QKeySequence("Ctrl+1"), self)
        self.shortcut_cut.activated.connect(lambda: self.add_annotation(annotation_type="cut"))
        
        self.shortcut_fade_start = QShortcut(QKeySequence("Ctrl+2"), self)
        self.shortcut_fade_start.activated.connect(lambda: self.add_annotation(annotation_type="fade_start"))
        
        self.shortcut_fade_end = QShortcut(QKeySequence("Ctrl+3"), self)
        self.shortcut_fade_end.activated.connect(lambda: self.add_annotation(annotation_type="fade_end"))
    
    def open_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开视频文件", "", "视频文件 (*.mp4 *.avi *.mkv *.mov *.wmv)"
        )
        
        if file_path:
            self.load_video(file_path)
    
    def load_video(self, video_path):
        # 关闭之前的视频
        if self.cap is not None:
            self.pause_video()
            self.cap.release()
        
        # 打开新视频
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        
        if not self.cap.isOpened():
            QMessageBox.critical(self, "错误", "无法打开视频文件！")
            return
        
        # 获取视频属性
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.duration = self.frame_count / self.fps
        
        # 设置进度条范围
        self.video_player.progress_slider.setMaximum(self.frame_count - 1)
        
        # 清空标注
        self.annotations = []
        self.annotation_widget.annotation_list.clear()
        self.fade_pairs = {}
        
        # 加载第一帧
        self.current_frame = 0
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        self.update_frame(initial=True)
        
        # 更新界面
        file_name = os.path.basename(video_path)
        self.setWindowTitle(f"视频标注工具 - {file_name}")
        self.statusBar().showMessage(f"已加载视频: {file_name}")
        
        # 尝试加载与视频同名的标注文件
        self.try_load_annotations(video_path)
    
    def try_load_annotations(self, video_path):
        annotation_path = os.path.splitext(video_path)[0] + "_annotations.json"
        
        if os.path.exists(annotation_path):
            try:
                with open(annotation_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.annotations = data.get('annotations', [])
                
                # 重建渐变配对
                self.fade_pairs = {}
                for anno in self.annotations:
                    if anno['type'] == 'fade_start':
                        self.fade_pairs[anno['id']] = None
                    elif anno['type'] == 'fade_end' and 'paired_with' in anno:
                        self.fade_pairs[anno['paired_with']] = anno['id']
                
                # 更新标注列表
                self.update_annotation_list()
                
                self.statusBar().showMessage(f"已加载标注: {len(self.annotations)} 条")
            except Exception as e:
                QMessageBox.warning(self, "警告", f"无法加载标注文件: {str(e)}")
    
    def update_frame(self, initial=False):
        if self.cap is None:
            return
        
        if not initial:
            # 读取当前帧
            ret, frame = self.cap.read()
            
            # 如果视频结束，停止播放
            if not ret:
                self.pause_video()
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_count - 1)
                ret, frame = self.cap.read()
                if not ret:
                    return
            
            self.current_frame += 1
        else:
            # 读取当前帧而不前进
            ret, frame = self.cap.read()
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            if not ret:
                return
        
        # 转换为RGB格式
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 调整帧大小以适应视频显示区域
        h, w, ch = frame_rgb.shape
        frame_size = self.video_player.video_frame.size()
        
        # 保持宽高比
        if w/h > frame_size.width()/frame_size.height():
            display_w = frame_size.width()
            display_h = int(h * display_w / w)
        else:
            display_h = frame_size.height()
            display_w = int(w * display_h / h)
        
        # 创建QImage
        bytes_per_line = ch * w
        q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        
        # 显示帧
        self.video_player.video_frame.setPixmap(pixmap.scaled(
            display_w, display_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        
        # 更新进度条和时间标签
        current_time = self.frame_to_time(self.current_frame)
        total_time = self.frame_to_time(self.frame_count)
        self.video_player.time_label.setText(f"{current_time} / {total_time}")
        
        # 更新进度条，但不触发事件
        self.video_player.progress_slider.blockSignals(True)
        self.video_player.progress_slider.setValue(self.current_frame)
        self.video_player.progress_slider.blockSignals(False)
    
    def frame_to_time(self, frame_number):
        seconds = frame_number / self.fps
        return str(timedelta(seconds=int(seconds)))
    
    def time_to_frame(self, time_str):
        h, m, s = map(int, time_str.split(':'))
        total_seconds = h * 3600 + m * 60 + s
        return int(total_seconds * self.fps)
    
    def play_video(self):
        if self.cap is None:
            return
        
        # 如果到达最后一帧，重新开始
        if self.current_frame >= self.frame_count - 1:
            self.current_frame = 0
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        
        self.playing = True
        self.video_player.play_button.setText("暂停")
        
        # 启动计时器，控制视频播放速度
        interval = int(1000 / self.fps)
        self.timer.start(interval)
    
    def pause_video(self):
        if self.cap is None:
            return
        
        self.playing = False
        self.video_player.play_button.setText("播放")
        self.timer.stop()
    
    def toggle_play(self):
        if self.playing:
            self.pause_video()
        else:
            self.play_video()
    
    def seek_relative(self, seconds=0, frames=0):
        if self.cap is None:
            return
        
        # 计算新的帧位置
        new_frame = self.current_frame
        
        if seconds != 0:
            new_frame += int(seconds * self.fps)
        
        if frames != 0:
            new_frame += frames
        
        # 确保新位置在有效范围内
        new_frame = max(0, min(new_frame, self.frame_count - 1))
        
        # 设置新位置
        self.set_position(new_frame)
    
    def set_position(self, frame_pos):
        if self.cap is None:
            return
        
        # 保存播放状态
        was_playing = self.playing
        if was_playing:
            self.pause_video()
        
        # 设置新位置
        self.current_frame = frame_pos
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        
        # 更新显示
        self.update_frame(initial=True)
        
        # 如果之前在播放，恢复播放
        if was_playing:
            self.play_video()
    
    def slider_pressed(self):
        self.was_playing = self.playing
        self.pause_video()
    
    def slider_released(self):
        frame_pos = self.video_player.progress_slider.value()
        self.set_position(frame_pos)
        if self.was_playing:
            self.play_video()
    
    def generate_annotation_id(self):
        return str(int(time.time() * 1000))
    
    def add_annotation(self, annotation_type):
        if self.cap is None:
            return
        
        # 暂停视频
        was_playing = self.playing
        if was_playing:
            self.pause_video()
        
        current_time = self.frame_to_time(self.current_frame)
        annotation_id = self.generate_annotation_id()
        
        annotation = {
            'id': annotation_id,
            'type': annotation_type,
            'frame': self.current_frame,
            'time': current_time,
            'timestamp': datetime.now().isoformat()
        }
        
        # 处理渐变标注配对
        if annotation_type == 'fade_start':
            self.fade_pairs[annotation_id] = None
        elif annotation_type == 'fade_end':
            # 查找最近的未配对的fade_start
            unpaired_starts = [aid for aid, end_id in self.fade_pairs.items() if end_id is None]
            if unpaired_starts:
                # 按时间顺序找最近的未配对的fade_start
                closest_start_id = None
                closest_start_frame = -1
                
                for start_id in unpaired_starts:
                    for a in self.annotations:
                        if a['id'] == start_id:
                            if closest_start_frame == -1 or a['frame'] > closest_start_frame:
                                closest_start_frame = a['frame']
                                closest_start_id = start_id
                
                if closest_start_id and closest_start_frame <= self.current_frame:
                    # 建立配对关系
                    annotation['paired_with'] = closest_start_id
                    self.fade_pairs[closest_start_id] = annotation_id
            
        # 添加标注
        self.annotations.append(annotation)
        
        # 按时间顺序排序
        self.annotations.sort(key=lambda x: x['frame'])
        
        # 更新标注列表
        self.update_annotation_list()
        
        # 如果之前在播放，恢复播放
        if was_playing:
            self.play_video()
    
    def update_annotation_list(self):
        # 清空列表
        self.annotation_widget.annotation_list.clear()
        
        # 添加排序后的标注
        for annotation in self.annotations:
            annotation_type = annotation['type']
            time_str = annotation['time']
            
            if annotation_type == 'cut':
                item_text = f"{time_str} - 直接切换"
            elif annotation_type == 'fade_start':
                # 检查是否有配对
                if annotation['id'] in self.fade_pairs and self.fade_pairs[annotation['id']] is not None:
                    item_text = f"{time_str} - 渐变开始"
                else:
                    item_text = f"{time_str} - 渐变开始 (未配对)"
            elif annotation_type == 'fade_end':
                if 'paired_with' in annotation:
                    item_text = f"{time_str} - 渐变结束"
                else:
                    item_text = f"{time_str} - 渐变结束 (未配对)"
            else:
                item_text = f"{time_str} - {annotation_type}"
            
            self.annotation_widget.annotation_list.addItem(item_text)
    
    def delete_selected_annotation(self):
        selected_indexes = self.annotation_widget.annotation_list.selectedIndexes()
        if not selected_indexes:
            return
        
        # 获取选中项的索引
        index = selected_indexes[0].row()
        
        if 0 <= index < len(self.annotations):
            annotation = self.annotations[index]
            
            # 处理渐变标注配对关系
            if annotation['type'] == 'fade_start' and annotation['id'] in self.fade_pairs:
                paired_end_id = self.fade_pairs[annotation['id']]
                if paired_end_id:
                    # 找到并更新配对的fade_end标注
                    for i, a in enumerate(self.annotations):
                        if a['id'] == paired_end_id:
                            if 'paired_with' in a:
                                del a['paired_with']
                
                # 删除配对关系
                del self.fade_pairs[annotation['id']]
            
            elif annotation['type'] == 'fade_end' and 'paired_with' in annotation:
                paired_start_id = annotation['paired_with']
                if paired_start_id in self.fade_pairs:
                    # 移除配对关系
                    self.fade_pairs[paired_start_id] = None
            
            # 删除标注
            self.annotations.pop(index)
            
            # 更新标注列表
            self.update_annotation_list()
    
    def save_annotations(self):
        if not self.video_path:
            QMessageBox.warning(self, "警告", "没有加载视频！")
            return
        
        # 准备保存数据
        data = {
            'video_file': os.path.basename(self.video_path),
            'frame_count': self.frame_count,
            'fps': self.fps,
            'duration': self.duration,
            'annotations': self.annotations,
            'saved_at': datetime.now().isoformat()
        }
        
        # 默认保存到与视频同名的文件
        default_path = os.path.splitext(self.video_path)[0] + "_annotations.json"
        
        # 让用户选择保存位置
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存标注", default_path, "JSON文件 (*.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                self.statusBar().showMessage(f"标注已保存至 {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存标注失败: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoAnnotatorApp()
    sys.exit(app.exec_()) 