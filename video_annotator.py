import sys
import cv2
import json
import csv
import os
import warnings
from datetime import timedelta
from collections import OrderedDict

import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLabel, QSlider, QFileDialog, QShortcut, 
                            QListWidget, QListWidgetItem, QComboBox, QMessageBox,
                            QGridLayout, QGroupBox, QSplitter, QFrame, QAction, QMenu, QStyle, QSizePolicy)
from PyQt5.QtGui import QImage, QPixmap, QKeySequence, QFont, QFontMetrics, QPainter
from PyQt5.QtCore import Qt, QTimer, QSize, QEvent

warnings.filterwarnings("ignore", category=DeprecationWarning)

class EllipsisLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_text = ""

        size_policy = self.sizePolicy()
        size_policy.setHorizontalPolicy(QSizePolicy.Expanding)
        size_policy.setVerticalPolicy(QSizePolicy.Preferred)
        self.setSizePolicy(size_policy)

    def setText(self, text):
        self.full_text = text
        self.setToolTip(text)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self.full_text, Qt.ElideRight, self.width())
        painter.drawText(self.rect(), self.alignment(), elided)

class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 将点击位置转换为滑块对应的数值
            new_value = QStyle.sliderValueFromPosition(
                self.minimum(), 
                self.maximum(), 
                event.x(), 
                self.width()
            )
            self.setValue(new_value)
            # 触发与拖动完成相同的逻辑
            self.sliderReleased.emit()
        super().mousePressEvent(event)

class VideoAnnotator(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("视频镜头边界标注工具")
        self.setGeometry(100, 100, 1280, 720)
        
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
        
        self.cache_enabled = True
        self.cache_size = 200  # 默认缓存200帧
        self.frame_cache = OrderedDict()  # 使用OrderedDict实现LRU缓存
        
        # 标注数据
        self.annotations = []
        self.temp_annotation = None  # 用于存储临时标注（对于模板2）
        
        # 设置UI
        self.init_ui()
        
        # 设置菜单
        self.create_menu()
        
        # 设置快捷键
        self.setup_shortcuts()
        
        # 禁用需要视频加载后才能使用的控件
        self.toggle_controls(False)
        
        # 安装事件过滤器以捕获键盘事件
        self.installEventFilter(self)
    
        # 新增一个标记，用来区分"是否需要跳转（随机访问视频帧）"
        # 当用户拖动进度条或快进/后退时，将其置为 True
        # 在 update_frame() 中检测到 True 时才执行 cap.set(...)
        self.need_jump = True
        # 新增一个标记，用来区分"是否正在拖动进度条"
        self.is_dragging = False

    def init_ui(self):
        # 主布局
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 创建一个分割器，将视频区域与标注区域分开
        splitter = QSplitter(Qt.Vertical)
        
        # ===== 视频区域 =====
        video_widget = QWidget()
        video_layout = QVBoxLayout(video_widget)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        # 视频显示区域
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setFrameShape(QFrame.Box)
        self.video_label.setFrameShadow(QFrame.Sunken)
        video_layout.addWidget(self.video_label)
        
        # 视频控制区域
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 5, 0, 0)
        
        # 时间和进度条布局
        time_slider_layout = QVBoxLayout()
        
        # 时间标签
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.time_label.setFont(font)
        time_slider_layout.addWidget(self.time_label)
        
        # 进度条
        # self.slider = QSlider(Qt.Horizontal)
        self.slider = ClickableSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(1000)
        self.slider.setValue(0)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)
        self.slider.valueChanged.connect(self.scrub_video)
        time_slider_layout.addWidget(self.slider)
        
        control_layout.addLayout(time_slider_layout)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 打开视频按钮
        self.open_btn = QPushButton("打开视频")
        self.open_btn.clicked.connect(self.open_video)
        button_layout.addWidget(self.open_btn)
        
        # 播放/暂停按钮
        self.play_btn = QPushButton("播放")
        self.play_btn.clicked.connect(self.toggle_play)
        button_layout.addWidget(self.play_btn)
        
        # 前进/后退按钮
        self.back_btn = QPushButton("后退5秒")
        self.back_btn.clicked.connect(lambda: self.seek_relative(-5))
        button_layout.addWidget(self.back_btn)
        
        self.forward_btn = QPushButton("前进5秒")
        self.forward_btn.clicked.connect(lambda: self.seek_relative(5))
        button_layout.addWidget(self.forward_btn)
        
        control_layout.addLayout(button_layout)
        
        video_layout.addWidget(control_widget)
        
        # 快捷键帮助组件
        shortcuts_box = QGroupBox("键盘快捷键")
        shortcuts_layout = QGridLayout()
        
        shortcuts = [
            ("右箭头", "前进5秒"),
            ("左箭头", "后退5秒"),
            ("Alt+右箭头", "前进1秒"),
            ("Alt+左箭头", "后退1秒"),
            ("Shift+右箭头", "前进5帧"),
            ("Shift+左箭头", "后退5帧"),
            ("空格", "播放/暂停"),
            ("Ctrl+1", "添加直接切换"),
            ("Ctrl+2", "添加渐变过渡")
        ]
        
        for i, (key, desc) in enumerate(shortcuts):
            key_label = QLabel(key)
            key_label.setStyleSheet("font-weight: bold;")
            desc_label = QLabel(desc)
            shortcuts_layout.addWidget(key_label, i // 3, (i % 3) * 2)
            shortcuts_layout.addWidget(desc_label, i // 3, (i % 3) * 2 + 1)
        
        shortcuts_box.setLayout(shortcuts_layout)
        video_layout.addWidget(shortcuts_box)
        
        # ===== 标注区域 =====
        annotation_widget = QWidget()
        annotation_layout = QHBoxLayout(annotation_widget)
        annotation_layout.setContentsMargins(0, 0, 0, 0)

        # 标注列表组
        annotation_list_group = QGroupBox("标注列表")
        annotation_list_layout = QVBoxLayout()
        
        # 标注列表
        self.annotation_list = QListWidget()
        self.annotation_list.setSelectionMode(QListWidget.SingleSelection)
        self.annotation_list.itemDoubleClicked.connect(self.jump_to_annotation)
        annotation_list_layout.addWidget(self.annotation_list)
        
        annotation_list_group.setLayout(annotation_list_layout)
        annotation_layout.addWidget(annotation_list_group, 2)
        
        # 标注控制组
        annotation_control_group = QGroupBox("控制")
        annotation_control_layout = QVBoxLayout()
        
        # 标注模板选择
        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("模板:"))
        
        self.template_combo = QComboBox()
        self.template_combo.addItem("1: 直接切换 (单次标注)")
        self.template_combo.addItem("2: 渐变过渡 (开始-结束对)")
        template_layout.addWidget(self.template_combo)
        
        annotation_control_layout.addLayout(template_layout)
        
        # 添加标注按钮
        self.add_annotation_btn = QPushButton("添加标注 (Ctrl+1/2)")
        self.add_annotation_btn.clicked.connect(self.add_annotation)
        annotation_control_layout.addWidget(self.add_annotation_btn)
        
        # 删除标注按钮
        self.delete_annotation_btn = QPushButton("删除选中标注")
        self.delete_annotation_btn.clicked.connect(self.delete_annotation)
        annotation_control_layout.addWidget(self.delete_annotation_btn)
        
        # 清除所有标注按钮
        self.clear_annotations_btn = QPushButton("清除所有标注")
        self.clear_annotations_btn.clicked.connect(self.clear_annotations)
        annotation_control_layout.addWidget(self.clear_annotations_btn)
        
        # 保存标注按钮
        self.save_annotation_btn = QPushButton("保存标注")
        self.save_annotation_btn.clicked.connect(self.save_annotations)
        annotation_control_layout.addWidget(self.save_annotation_btn)
        
        # 加载标注按钮
        self.load_annotation_btn = QPushButton("加载标注")
        self.load_annotation_btn.clicked.connect(self.load_annotations)
        annotation_control_layout.addWidget(self.load_annotation_btn)
        
        # 当前标注状态
        # self.status_label = QLabel("未加载视频")
        self.status_label = EllipsisLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold;")
        annotation_control_layout.addWidget(self.status_label)
        
        annotation_control_group.setLayout(annotation_control_layout)
        annotation_layout.addWidget(annotation_control_group, 1)

        # 让左右各占一半宽度
        annotation_layout.setStretch(0, 1)
        annotation_layout.setStretch(1, 1)
        
        # 添加到分割器
        splitter.addWidget(video_widget)
        splitter.addWidget(annotation_widget)
        
        # 设置初始大小
        splitter.setSizes([500, 220])
        
        main_layout.addWidget(splitter)
        
        self.setCentralWidget(main_widget)
    
    def sort_annotations(self):
        """
        根据帧号进行排序：direct_cut 使用 frame，gradual 使用 start_frame
        """
        def annotation_sort_key(anno):
            if anno["type"] == "direct_cut":
                return anno["frame"]
            else:  # gradual
                return anno["start_frame"]
        self.annotations.sort(key=annotation_sort_key)

    def refresh_annotation_list(self):
        """
        根据当前 self.annotations 刷新列表显示
        """
        self.annotation_list.clear()
        for anno in self.annotations:
            if anno["type"] == "direct_cut":
                item_text = f"直接切换于 {anno['time']} (帧 {anno['frame']})"
            else:
                item_text = (
                    f"渐变过渡: {anno['start_time']} - {anno['end_time']} "
                    f"(帧 {anno['start_frame']} - {anno['end_frame']})"
                )
            self.annotation_list.addItem(item_text)

    def scrub_video(self, value):
        """
        鼠标拖拽滑块时（包括从轨道外点击并立即拖动），实时更新画面。
        """
        if self.cap is None:
            return

        # 暂停播放（可根据需要决定是否保持播放状态）
        # if self.playing:
        #     self.toggle_play()
        #     self._was_playing = True

        # 将当前拖拽位置映射到帧数，保存为 self.current_frame
        self.current_frame = value
        # 如果想要"实时"预览，则需要标记"需要跳转"并立刻刷新
        if self.is_dragging:
            self.need_jump = True
            self.update_frame()

    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu('文件')
        
        # 打开视频
        open_action = QAction('打开视频', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_video)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        # 加载标注
        load_action = QAction('加载标注', self)
        load_action.setShortcut('Ctrl+L')
        load_action.triggered.connect(self.load_annotations)
        file_menu.addAction(load_action)
        
        # 保存标注
        save_action = QAction('保存标注', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_annotations)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        # 退出
        exit_action = QAction('退出', self)
        exit_action.setShortcut('Alt+F4')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 播放菜单
        playback_menu = menubar.addMenu('播放')
        
        # 播放/暂停
        self.play_action = QAction('播放/暂停', self)
        self.play_action.setShortcut('Space')
        self.play_action.triggered.connect(self.toggle_play)
        playback_menu.addAction(self.play_action)
        
        # 向前跳转
        forward_menu = QMenu('前进', self)
        
        self.forward_5s_action = QAction('前进5秒', self)
        self.forward_5s_action.setShortcut('Right')
        self.forward_5s_action.triggered.connect(lambda: self.seek_relative(5))
        forward_menu.addAction(self.forward_5s_action)
        
        self.forward_1s_action = QAction('前进1秒', self)
        self.forward_1s_action.setShortcut('Alt+Right')
        self.forward_1s_action.triggered.connect(lambda: self.seek_relative(1))
        forward_menu.addAction(self.forward_1s_action)
        
        self.forward_5f_action = QAction('前进5帧', self)
        self.forward_5f_action.setShortcut('Shift+Right')
        self.forward_5f_action.triggered.connect(lambda: self.seek_frames(5))
        forward_menu.addAction(self.forward_5f_action)
        
        playback_menu.addMenu(forward_menu)
        
        # 向后跳转
        backward_menu = QMenu('后退', self)
        
        self.backward_5s_action = QAction('后退5秒', self)
        self.backward_5s_action.setShortcut('Left')
        self.backward_5s_action.triggered.connect(lambda: self.seek_relative(-5))
        backward_menu.addAction(self.backward_5s_action)
        
        self.backward_1s_action = QAction('后退1秒', self)
        self.backward_1s_action.setShortcut('Alt+Left')
        self.backward_1s_action.triggered.connect(lambda: self.seek_relative(-1))
        backward_menu.addAction(self.backward_1s_action)
        
        self.backward_5f_action = QAction('后退5帧', self)
        self.backward_5f_action.setShortcut('Shift+Left')
        self.backward_5f_action.triggered.connect(lambda: self.seek_frames(-5))
        backward_menu.addAction(self.backward_5f_action)
        
        playback_menu.addMenu(backward_menu)
        
        # 标注菜单
        annotation_menu = menubar.addMenu('标注')
        
        # 添加标注
        self.add_direct_action = QAction('添加直接切换', self)
        self.add_direct_action.setShortcut('Ctrl+1')
        self.add_direct_action.triggered.connect(lambda: self.add_annotation_with_template(0))
        annotation_menu.addAction(self.add_direct_action)
        
        self.add_gradual_action = QAction('添加渐变过渡', self)
        self.add_gradual_action.setShortcut('Ctrl+2')
        self.add_gradual_action.triggered.connect(lambda: self.add_annotation_with_template(1))
        annotation_menu.addAction(self.add_gradual_action)
        
        annotation_menu.addSeparator()
        
        # 删除标注
        self.delete_action = QAction('删除选中标注', self)
        self.delete_action.setShortcut('Delete')
        self.delete_action.triggered.connect(self.delete_annotation)
        annotation_menu.addAction(self.delete_action)
        
        # 清除所有标注
        clear_action = QAction('清除所有标注', self)
        clear_action.triggered.connect(self.clear_annotations)
        annotation_menu.addAction(clear_action)
    
    def toggle_controls(self, enabled=True):
        """启用/禁用需要视频加载才能使用的控件"""
        self.play_btn.setEnabled(enabled)
        self.back_btn.setEnabled(enabled)
        self.forward_btn.setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.add_annotation_btn.setEnabled(enabled)
        self.delete_annotation_btn.setEnabled(enabled)
        self.clear_annotations_btn.setEnabled(enabled)
        self.save_annotation_btn.setEnabled(enabled)
        
    def configure_cache(self, enabled=True, size=200):
        """配置帧缓存设置
        
        Args:
            enabled (bool): 是否启用缓存
            size (int): 缓存的最大帧数
        """
        self.cache_enabled = enabled
        self.cache_size = size
        
        if not enabled:
            self.frame_cache.clear()
        elif len(self.frame_cache) > size:
            while len(self.frame_cache) > size:
                self.frame_cache.popitem(last=False)
    
    def setup_shortcuts(self):
        """设置快捷键
        注：所有快捷键已在创建菜单时设置，此处不再重复设置
        """
        pass
    
    def eventFilter(self, obj, event):
        """全局事件过滤器，捕获键盘事件"""
        if event.type() == QEvent.KeyPress:
            # 在任何地方都能响应键盘快捷键
            return False  # 让快捷键系统处理这个事件
        return super().eventFilter(obj, event)
    
    def open_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "打开视频", "", "视频文件 (*.mp4 *.avi *.mkv *.mov)")
        
        if not file_path:
            return
        
        # 关闭之前打开的视频
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        
        self.frame_cache.clear()
        
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
            
            # 清空标注
            self.annotations = []
            self.annotation_list.clear()
            self.temp_annotation = None
            
            # 设置窗口标题
            self.setWindowTitle(f"视频镜头边界标注工具 - {os.path.basename(file_path)}")
            
            # 启用控件
            self.toggle_controls(True)
            
            # 更新状态
            self.status_label.setText(f"已加载: {os.path.basename(file_path)} ({self.video_width}x{self.video_height})")
            
            # 根据视频长宽比调整界面布局
            self.adjust_layout_for_video()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开视频失败: {str(e)}")
            self.cap = None
            self.toggle_controls(False)
    
    def update_frame(self):
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
            
            rgb_frame = None
            if self.cache_enabled and self.current_frame in self.frame_cache:
                rgb_frame = self.frame_cache[self.current_frame]
                self.frame_cache.pop(self.current_frame)
                self.frame_cache[self.current_frame] = rgb_frame
            else:
                if self.need_jump:
                    # 只有在需要跳转时才调用 cap.set
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
                    self.need_jump = False
                
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
                
                # 转换颜色空间
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                if self.cache_enabled:
                    if len(self.frame_cache) >= self.cache_size:
                        self.frame_cache.popitem(last=False)  # 移除OrderedDict中的第一项（最旧的）
                    self.frame_cache[self.current_frame] = rgb_frame.copy()
            
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
                elif self.cache_enabled and self.current_frame + 1 < self.frame_count and self.current_frame + 1 not in self.frame_cache:
                    current_pos = self.current_frame
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame + 1)
                    ret, next_frame = self.cap.read()
                    if ret:
                        next_rgb_frame = cv2.cvtColor(next_frame, cv2.COLOR_BGR2RGB)
                        if len(self.frame_cache) >= self.cache_size:
                            self.frame_cache.popitem(last=False)
                        self.frame_cache[self.current_frame + 1] = next_rgb_frame.copy()
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            
        except Exception as e:
            self.timer.stop()
            self.playing = False
            self.play_btn.setText("播放")
            QMessageBox.critical(self, "错误", f"显示帧时出错: {str(e)}")
    
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
    
    def slider_released(self):
        """释放滑块后跳转到相应位置"""
        self.current_frame = self.slider.value()
        self.is_dragging = False
        self.need_jump = True
        self.update_frame()
        
        # 如果之前是播放状态，则恢复播放
        if self._was_playing:
            self.toggle_play()
        # 重置状态，防止残留
        self._was_playing = False

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
    
    def jump_to_annotation(self, item):
        """双击标注项跳转到对应位置"""
        idx = self.annotation_list.row(item)
        
        if idx < 0 or idx >= len(self.annotations):
            return
        
        anno = self.annotations[idx]
        if anno["type"] == "direct_cut":
            target_frame = anno["frame"]
        else:  # gradual
            target_frame = anno["start_frame"]
        
        self.current_frame = target_frame
        self.need_jump = True
        self.update_frame()
    
    def add_annotation_with_template(self, template_index):
        """使用指定模板添加标注"""
        if self.cap is None:
            return
        
        self.template_combo.setCurrentIndex(template_index)
        self.add_annotation()
    
    def add_annotation(self):
        """添加标注"""
        if self.cap is None:
            QMessageBox.warning(self, "警告", "请先打开视频文件。")
            return
        
        template_index = self.template_combo.currentIndex()
        current_time = self.frame_to_time(self.current_frame)
        
        if template_index == 0:  # 模板1：直接切换
            annotation = {
                "type": "direct_cut",
                "time": current_time,
                "frame": self.current_frame
            }
            self.annotations.append(annotation)
            item_text = f"直接切换于 {current_time} (帧 {self.current_frame})"
            self.annotation_list.addItem(item_text)
            self.status_label.setText(f"已添加: {item_text}")
        
        elif template_index == 1:  # 模板2：渐变过渡
            if self.temp_annotation is None:  # 开始标注
                self.temp_annotation = {
                    "type": "gradual",
                    "start_time": current_time,
                    "start_frame": self.current_frame,
                    "end_time": None,
                    "end_frame": None
                }
                item_text = f"渐变过渡开始于 {current_time} (帧 {self.current_frame})"
                self.annotation_list.addItem(item_text)
                self.status_label.setText("已开始渐变过渡标注。请用Ctrl+2标记结束位置。")
            else:  # 结束标注
                if self.current_frame <= self.temp_annotation["start_frame"]:
                    QMessageBox.warning(self, "警告", "结束帧必须在开始帧之后。")
                    return
                
                self.temp_annotation["end_time"] = current_time
                self.temp_annotation["end_frame"] = self.current_frame
                self.annotations.append(self.temp_annotation)
                
                # 更新列表项
                self.annotation_list.takeItem(self.annotation_list.count() - 1)
                item_text = (f"渐变过渡: {self.temp_annotation['start_time']} - {current_time} "
                           f"(帧 {self.temp_annotation['start_frame']} - {self.current_frame})")
                self.annotation_list.addItem(item_text)
                self.status_label.setText(f"已添加: {item_text}")
                
                self.temp_annotation = None
        
        # 滚动到最新添加的项
        # self.annotation_list.scrollToBottom()
        self.sort_annotations()
        self.refresh_annotation_list()
    
    def delete_annotation(self):
        """删除选中的标注"""
        current_row = self.annotation_list.currentRow()
        if current_row == -1:
            QMessageBox.warning(self, "警告", "请选择要删除的标注。")
            return
        
        # 如果是临时标注状态，需要重置
        if self.temp_annotation is not None and current_row == self.annotation_list.count() - 1:
            self.temp_annotation = None
            self.status_label.setText("已取消渐变过渡标注")
        else:
            deleted_annotation = self.annotations.pop(current_row)
            self.status_label.setText(f"已删除于 {deleted_annotation.get('time', '') or deleted_annotation.get('start_time', '')} 的标注")
        
        self.annotation_list.takeItem(current_row)

        self.sort_annotations()
        self.refresh_annotation_list()
    
    def clear_annotations(self):
        """清除所有标注"""
        if not self.annotations and self.temp_annotation is None:
            return
        
        reply = QMessageBox.question(self, "清除标注", 
                                    "确定要清除所有标注吗？",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.annotations = []
            self.annotation_list.clear()
            self.temp_annotation = None
            self.status_label.setText("已清除所有标注")
    
    def save_annotations(self):
        """保存标注"""
        if not self.annotations and self.temp_annotation is None:
            QMessageBox.warning(self, "警告", "没有标注可保存。")
            return
        
        # 如果有临时标注未完成，提示用户
        if self.temp_annotation is not None:
            reply = QMessageBox.question(self, "未完成的标注", 
                                        "你有一个未完成的渐变过渡标注。要舍弃它吗？",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        # 如果有视频文件，使用视频文件名作为默认保存名
        default_name = ""
        if self.video_path:
            base_name = os.path.splitext(os.path.basename(self.video_path))[0]
            default_name = f"{base_name}_annotations"
        
        file_path, filter_used = QFileDialog.getSaveFileName(self, "保存标注", default_name, 
                                                 "JSON文件 (*.json);;CSV文件 (*.csv)")
        
        if not file_path:
            return
        
        # 根据选择的过滤器确保文件扩展名正确
        if filter_used == "JSON文件 (*.json)" and not file_path.lower().endswith('.json'):
            file_path += '.json'
        elif filter_used == "CSV文件 (*.csv)" and not file_path.lower().endswith('.csv'):
            file_path += '.csv'
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_ext == '.json':
                self.save_as_json(file_path)
            elif file_ext == '.csv':
                self.save_as_csv(file_path)
            else:
                QMessageBox.warning(self, "警告", "不支持的文件格式。请使用.json或.csv")
                return
            
            QMessageBox.information(self, "成功", f"标注已保存到 {file_path}")
            self.status_label.setText(f"已保存{len(self.annotations)}个标注到 {os.path.basename(file_path)}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存标注失败: {str(e)}")
    
    def load_annotations(self):
        """加载标注"""
        file_path, _ = QFileDialog.getOpenFileName(self, "加载标注", "", 
                                                 "JSON文件 (*.json);;CSV文件 (*.csv);;所有文件 (*)")
        
        if not file_path:
            return
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_ext == '.json':
                self.load_from_json(file_path)
            elif file_ext == '.csv':
                self.load_from_csv(file_path)
            else:
                QMessageBox.warning(self, "警告", "不支持的文件格式。请使用.json或.csv")
                return
            
            QMessageBox.information(self, "成功", f"已从 {file_path} 加载 {len(self.annotations)} 个标注")
            self.status_label.setText(f"已从 {os.path.basename(file_path)} 加载 {len(self.annotations)} 个标注")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载标注失败: {str(e)}")
    
    def save_as_json(self, file_path):
        """将标注保存为JSON格式"""
        if not self.video_path:
            raise ValueError("未加载视频")
        
        video_info = {
            "filename": os.path.basename(self.video_path),
            "filepath": self.video_path,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "duration": self.frame_to_time(self.frame_count)
        }
        
        data = {
            "video_info": video_info,
            "annotations": self.annotations
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def save_as_csv(self, file_path):
        """将标注保存为CSV格式"""
        headers = ["type", "start_time", "start_frame", "end_time", "end_frame"]
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for anno in self.annotations:
                row = {}
                if anno["type"] == "direct_cut":
                    row = {
                        "type": "direct_cut",
                        "start_time": anno["time"],
                        "start_frame": anno["frame"],
                        "end_time": "",
                        "end_frame": ""
                    }
                else:  # gradual
                    row = {
                        "type": "gradual",
                        "start_time": anno["start_time"],
                        "start_frame": anno["start_frame"],
                        "end_time": anno["end_time"],
                        "end_frame": anno["end_frame"]
                    }
                writer.writerow(row)
    
    def load_from_json(self, file_path):
        """从JSON文件加载标注"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 清除现有标注
        self.annotations = []
        self.annotation_list.clear()
        self.temp_annotation = None
        
        # 检查是否需要加载视频
        if self.cap is None and 'video_info' in data and 'filepath' in data['video_info']:
            video_path = data['video_info']['filepath']
            if os.path.exists(video_path):
                reply = QMessageBox.question(self, "加载视频", 
                                            f"是否加载关联的视频文件？\n{video_path}",
                                            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if reply == QMessageBox.Yes:
                    self.video_path = video_path
                    self.open_video()
        
        # 加载标注
        if 'annotations' in data:
            self.annotations = data['annotations']
            
            # 更新列表
            for anno in self.annotations:
                if anno["type"] == "direct_cut":
                    item_text = f"直接切换于 {anno['time']} (帧 {anno['frame']})"
                else:  # gradual
                    item_text = (f"渐变过渡: {anno['start_time']} - {anno['end_time']} "
                               f"(帧 {anno['start_frame']} - {anno['end_frame']})")
                self.annotation_list.addItem(item_text)
    
        self.sort_annotations()
        self.refresh_annotation_list()
    
    def load_from_csv(self, file_path):
        """从CSV文件加载标注"""
        # 清除现有标注
        self.annotations = []
        self.annotation_list.clear()
        self.temp_annotation = None
        
        with open(file_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                if row["type"] == "direct_cut":
                    annotation = {
                        "type": "direct_cut",
                        "time": row["start_time"],
                        "frame": int(row["start_frame"])
                    }
                    self.annotations.append(annotation)
                    item_text = f"直接切换于 {row['start_time']} (帧 {row['start_frame']})"
                else:  # gradual
                    annotation = {
                        "type": "gradual",
                        "start_time": row["start_time"],
                        "start_frame": int(row["start_frame"]),
                        "end_time": row["end_time"],
                        "end_frame": int(row["end_frame"])
                    }
                    self.annotations.append(annotation)
                    item_text = (f"渐变过渡: {row['start_time']} - {row['end_time']} "
                               f"(帧 {row['start_frame']} - {row['end_frame']})")
                
                self.annotation_list.addItem(item_text)
        
        self.sort_annotations()
        self.refresh_annotation_list()
    
    def closeEvent(self, event):
        """关闭窗口时释放资源"""
        if self.cap is not None:
            self.cap.release()
        event.accept()

    def adjust_layout_for_video(self):
        """根据视频长宽比调整界面布局"""
        if self.video_width <= 0 or self.video_height <= 0:
            return
        
        # 计算视频长宽比
        aspect_ratio = self.video_width / self.video_height
        
        # 获取当前窗口大小
        window_width = self.width()
        window_height = self.height()
        
        # 根据视频长宽比和当前窗口大小计算合适的视频显示区域大小
        video_area_height = int(window_height * 0.6)  # 视频区域占窗口高度的60%
        video_area_width = int(video_area_height * aspect_ratio)
        
        # 如果计算出的宽度超过窗口宽度，则根据宽度重新调整
        if video_area_width > window_width * 0.9:  # 留出10%的边距
            video_area_width = int(window_width * 0.9)
            video_area_height = int(video_area_width / aspect_ratio)
        
        # 设置视频标签的最小大小以适应视频比例
        self.video_label.setMinimumSize(video_area_width, video_area_height)
        
        # 调整窗口大小以更好地适应视频
        new_window_width = max(window_width, video_area_width + 40)  # 添加一些边距
        new_window_height = max(window_height, video_area_height + 320)  # 为控制和标注区域留出空间
        
        # 调整窗口大小，但不要超过屏幕大小的80%
        screen_rect = QApplication.desktop().screenGeometry()
        max_width = int(screen_rect.width() * 0.8)
        max_height = int(screen_rect.height() * 0.8)
        
        new_window_width = min(new_window_width, max_width)
        new_window_height = min(new_window_height, max_height)
        
        # 调整窗口大小
        self.resize(new_window_width, new_window_height)
        
        # 强制更新布局
        self.centralWidget().layout().activate()
        
        # 更新显示的第一帧
        self.update_frame()

    def resizeEvent(self, event):
        """窗口大小调整事件，用于调整视频显示"""
        super().resizeEvent(event)
        
        # 如果已加载视频，在窗口大小改变时更新帧显示
        if self.cap is not None:
            self.update_frame()

def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle('Fusion')
    
    window = VideoAnnotator()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
