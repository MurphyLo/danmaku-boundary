import sys
import os
import warnings
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLabel, QFileDialog, QShortcut, 
                            QListWidget, QComboBox, QMessageBox,
                            QGridLayout, QGroupBox, QSplitter, QFrame, QAction, QMenu)
from PyQt5.QtGui import QFont, QDragEnterEvent, QDropEvent
from PyQt5.QtCore import Qt, QEvent, QMimeData

# 导入自定义组件
from ui_components import EllipsisLabel, ClickableSlider
from annotation_manager import AnnotationManager
from video_player import VideoPlayer

warnings.filterwarnings("ignore", category=DeprecationWarning)

class VideoAnnotator(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("视频镜头边界标注工具")
        self.setGeometry(100, 100, 1280, 720)
        
        # 创建标注管理器（在UI初始化前）
        self.annotation_manager = AnnotationManager(self)
        
        # 设置UI
        self.init_ui()
        
        # 创建视频播放器
        self.video_player = VideoPlayer(self)
        self.setup_video_player()
        
        # 设置菜单
        self.create_menu()
        
        # 设置快捷键
        self.setup_shortcuts()
        
        # 禁用需要视频加载后才能使用的控件
        self.toggle_controls(False)
        
        # 安装事件过滤器以捕获键盘事件
        self.installEventFilter(self)
        
        # 连接列表双击事件
        self.annotation_list.itemDoubleClicked.connect(self.annotation_manager.jump_to_annotation)
        
        # 开启接收拖放
        self.setAcceptDrops(True)
    
    def setup_video_player(self):
        """设置视频播放器和UI元素的连接"""
        self.video_player.setup_ui_connections(
            self.video_label,
            self.time_label,
            self.slider,
            self.play_btn,
            self.preview_btn
        )
        
        # 连接前进后退按钮
        self.back_btn.clicked.connect(lambda: self.video_player.seek_relative(-5))
        self.forward_btn.clicked.connect(lambda: self.video_player.seek_relative(5))

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
        self.slider = ClickableSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(1000)
        self.slider.setValue(0)
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
        button_layout.addWidget(self.play_btn)
        
        # 前进/后退按钮
        self.back_btn = QPushButton("后退5秒")
        button_layout.addWidget(self.back_btn)
        
        self.forward_btn = QPushButton("前进5秒")
        button_layout.addWidget(self.forward_btn)

        # 快速预览按钮
        self.preview_btn = QPushButton("快速预览")
        button_layout.addWidget(self.preview_btn)
        
        control_layout.addLayout(button_layout)
        
        video_layout.addWidget(control_widget)
        
        # 快捷键帮助组件
        shortcuts_box = QGroupBox("键盘快捷键")
        shortcuts_layout = QGridLayout()
        
        shortcuts = [
            ("左箭头", "后退5秒"),
            ("右箭头", "前进5秒"),
            ("空格", "播放/暂停"),
            ("Alt+左箭头", "后退1秒"),
            ("Alt+右箭头", "前进1秒"),
            ("Ctrl+1", "添加直接切换"),
            ("Shift+左箭头", "后退5帧"),
            ("Shift+右箭头", "前进5帧"),
            ("Ctrl+2", "添加渐变过渡"),
            ("Ctrl+左箭头", "跳到上一标注点"),
            ("Ctrl+右箭头", "跳到下一标注点"),
            ("Ctrl+Q", "切换快速预览模式"),
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
        # 延迟连接双击事件，因为初始化时annotation_manager已存在但尚未连接UI信号
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
        self.add_annotation_btn.clicked.connect(self.annotation_manager.add_annotation)
        annotation_control_layout.addWidget(self.add_annotation_btn)
        
        # 删除标注按钮
        self.delete_annotation_btn = QPushButton("删除选中标注")
        self.delete_annotation_btn.clicked.connect(self.annotation_manager.delete_annotation)
        annotation_control_layout.addWidget(self.delete_annotation_btn)
        
        # 清除所有标注按钮
        self.clear_annotations_btn = QPushButton("清除所有标注")
        self.clear_annotations_btn.clicked.connect(self.annotation_manager.clear_annotations)
        annotation_control_layout.addWidget(self.clear_annotations_btn)
        
        # 保存标注按钮
        self.save_annotation_btn = QPushButton("保存标注")
        self.save_annotation_btn.clicked.connect(self.annotation_manager.save_annotations)
        annotation_control_layout.addWidget(self.save_annotation_btn)
        
        # 加载标注按钮
        self.load_annotation_btn = QPushButton("加载标注")
        self.load_annotation_btn.clicked.connect(self.annotation_manager.load_annotations)
        annotation_control_layout.addWidget(self.load_annotation_btn)
        
        # 当前标注状态
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
        load_action.triggered.connect(self.annotation_manager.load_annotations)
        file_menu.addAction(load_action)
        
        # 保存标注
        save_action = QAction('保存标注', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.annotation_manager.save_annotations)
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
        self.play_action.triggered.connect(self.video_player.toggle_play)
        playback_menu.addAction(self.play_action)
        
        # 快速预览模式
        self.preview_action = QAction('快速预览模式', self)
        self.preview_action.setShortcut('Ctrl+Q')
        self.preview_action.triggered.connect(self.video_player.toggle_preview_mode)
        playback_menu.addAction(self.preview_action)
        
        # 向前跳转
        forward_menu = QMenu('前进', self)
        
        self.forward_5s_action = QAction('前进5秒', self)
        self.forward_5s_action.setShortcut('Right')
        self.forward_5s_action.triggered.connect(lambda: self.video_player.seek_relative(5))
        forward_menu.addAction(self.forward_5s_action)
        
        self.forward_1s_action = QAction('前进1秒', self)
        self.forward_1s_action.setShortcut('Alt+Right')
        self.forward_1s_action.triggered.connect(lambda: self.video_player.seek_relative(1))
        forward_menu.addAction(self.forward_1s_action)
        
        self.forward_5f_action = QAction('前进5帧', self)
        self.forward_5f_action.setShortcut('Shift+Right')
        self.forward_5f_action.triggered.connect(lambda: self.video_player.seek_frames(5))
        forward_menu.addAction(self.forward_5f_action)
        
        playback_menu.addMenu(forward_menu)
        
        # 向后跳转
        backward_menu = QMenu('后退', self)
        
        self.backward_5s_action = QAction('后退5秒', self)
        self.backward_5s_action.setShortcut('Left')
        self.backward_5s_action.triggered.connect(lambda: self.video_player.seek_relative(-5))
        backward_menu.addAction(self.backward_5s_action)
        
        self.backward_1s_action = QAction('后退1秒', self)
        self.backward_1s_action.setShortcut('Alt+Left')
        self.backward_1s_action.triggered.connect(lambda: self.video_player.seek_relative(-1))
        backward_menu.addAction(self.backward_1s_action)
        
        self.backward_5f_action = QAction('后退5帧', self)
        self.backward_5f_action.setShortcut('Shift+Left')
        self.backward_5f_action.triggered.connect(lambda: self.video_player.seek_frames(-5))
        backward_menu.addAction(self.backward_5f_action)
        
        playback_menu.addMenu(backward_menu)
        
        # 添加在标注点之间跳转的菜单项
        jump_menu = QMenu('标注点间跳转', self)
        
        self.jump_prev_anno_action = QAction('跳转到上一标注点', self)
        self.jump_prev_anno_action.setShortcut('Ctrl+Left')
        self.jump_prev_anno_action.triggered.connect(self.video_player.jump_to_previous_annotation)
        jump_menu.addAction(self.jump_prev_anno_action)
        
        self.jump_next_anno_action = QAction('跳转到下一标注点', self)
        self.jump_next_anno_action.setShortcut('Ctrl+Right')
        self.jump_next_anno_action.triggered.connect(self.video_player.jump_to_next_annotation)
        jump_menu.addAction(self.jump_next_anno_action)
        
        playback_menu.addMenu(jump_menu)
        
        # 标注菜单
        annotation_menu = menubar.addMenu('标注')
        
        # 添加标注
        self.add_direct_action = QAction('添加直接切换', self)
        self.add_direct_action.setShortcut('Ctrl+1')
        self.add_direct_action.triggered.connect(lambda: self.annotation_manager.add_annotation_with_template(0))
        annotation_menu.addAction(self.add_direct_action)
        
        self.add_gradual_action = QAction('添加渐变过渡', self)
        self.add_gradual_action.setShortcut('Ctrl+2')
        self.add_gradual_action.triggered.connect(lambda: self.annotation_manager.add_annotation_with_template(1))
        annotation_menu.addAction(self.add_gradual_action)
        
        annotation_menu.addSeparator()
        
        # 删除标注
        self.delete_action = QAction('删除选中标注', self)
        self.delete_action.setShortcut('Delete')
        self.delete_action.triggered.connect(self.annotation_manager.delete_annotation)
        annotation_menu.addAction(self.delete_action)
        
        # 清除所有标注
        clear_action = QAction('清除所有标注', self)
        clear_action.triggered.connect(self.annotation_manager.clear_annotations)
        annotation_menu.addAction(clear_action)
    
    def toggle_controls(self, enabled=True):
        """启用/禁用需要视频加载后才能使用的控件"""
        self.play_btn.setEnabled(enabled)
        self.back_btn.setEnabled(enabled)
        self.forward_btn.setEnabled(enabled)
        self.preview_btn.setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.add_annotation_btn.setEnabled(enabled)
        self.delete_annotation_btn.setEnabled(enabled)
        self.clear_annotations_btn.setEnabled(enabled)
        self.save_annotation_btn.setEnabled(enabled)
    
    def setup_shortcuts(self):
        """设置快捷键 (所有快捷键已在创建菜单时设置) """
        pass
    
    def eventFilter(self, obj, event):
        """全局事件过滤器，捕获键盘事件"""
        if event.type() == QEvent.KeyPress:
            # 在任何地方都能响应键盘快捷键
            return False  # 让快捷键系统处理这个事件
        return super().eventFilter(obj, event)
    
    def open_video(self):
        """打开视频文件"""
        success = self.video_player.open_video()
        
        if success:
            # 设置窗口标题
            file_name = os.path.basename(self.video_player.video_path)
            self.setWindowTitle(f"视频镜头边界标注工具 - {file_name}")
            
            # 重置标注管理器
            self.annotation_manager.reset()
            
            # 启用控件
            self.toggle_controls(True)
            
            # 更新状态
            self.status_label.setText(
                f"已加载: {file_name} ({self.video_player.video_width}x{self.video_player.video_height})"
            )
            
            # 调整界面布局
            self.adjust_layout_for_video()
    
    def request_open_video(self, file_path):
        """处理来自AnnotationManager的打开视频请求"""
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "警告", f"视频文件不存在: {file_path}")
            return False
        
        self.video_player.video_path = file_path
        return self.video_player.open_video(file_path)
    
    def seek_to_frame(self, frame):
        """提供给AnnotationManager的跳转到指定帧的方法"""
        self.video_player.seek_to_frame(frame)
    
    def frame_to_time(self, frame_number):
        """提供给AnnotationManager的帧到时间的转换方法"""
        return self.video_player.frame_to_time(frame_number)
    
    def adjust_layout_for_video(self):
        """根据视频长宽比调整界面布局"""
        if not hasattr(self.video_player, 'video_width') or self.video_player.video_width <= 0 or self.video_player.video_height <= 0:
            return
        
        # 计算视频长宽比
        aspect_ratio = self.video_player.video_width / self.video_player.video_height
        
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
        self.video_player.update_frame()

    def resizeEvent(self, event):
        """窗口大小调整事件，用于调整视频显示"""
        super().resizeEvent(event)
        
        # 如果已加载视频，在窗口大小改变时更新帧显示
        if hasattr(self.video_player, 'cap') and self.video_player.cap is not None:
            self.video_player.update_frame()
    
    def closeEvent(self, event):
        """关闭窗口时释放资源"""
        self.video_player.close()
        event.accept()

    def dragEnterEvent(self, event: QDragEnterEvent):
        """处理拖动进入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        """处理放下事件"""
        urls = event.mimeData().urls()
        if not urls:
            return
        
        # 只处理第一个文件
        file_path = urls[0].toLocalFile()
        
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "警告", f"文件不存在: {file_path}")
            return
        
        # 获取文件扩展名
        _, ext = os.path.splitext(file_path.lower())
        
        # 视频文件扩展名
        video_exts = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv']
        # 标注文件扩展名
        annotation_exts = ['.json', '.csv']
        
        if ext in video_exts:
            # 打开视频文件
            self.video_player.video_path = file_path
            success = self.video_player.open_video(file_path)
            
            if success:
                # 设置窗口标题
                file_name = os.path.basename(self.video_player.video_path)
                self.setWindowTitle(f"视频镜头边界标注工具 - {file_name}")
                
                # 重置标注管理器
                self.annotation_manager.reset()
                
                # 启用控件
                self.toggle_controls(True)
                
                # 更新状态
                self.status_label.setText(
                    f"已加载: {file_name} ({self.video_player.video_width}x{self.video_player.video_height})"
                )
                
                # 调整界面布局
                self.adjust_layout_for_video()
                
        elif ext in annotation_exts:
            # 加载标注文件
            try:
                if ext == '.json':
                    self.annotation_manager.load_from_json(file_path)
                elif ext == '.csv':
                    self.annotation_manager.load_from_csv(file_path)
                
                self.annotation_manager.sort_annotations()
                self.annotation_manager.refresh_annotation_list()
                
                QMessageBox.information(self, "成功", f"已从 {file_path} 加载 {len(self.annotation_manager.annotations)} 个标注")
                self.status_label.setText(f"已从 {os.path.basename(file_path)} 加载 {len(self.annotation_manager.annotations)} 个标注")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载标注失败: {str(e)}")
        else:
            QMessageBox.warning(self, "警告", f"不支持的文件类型: {ext}")
        
        event.acceptProposedAction()