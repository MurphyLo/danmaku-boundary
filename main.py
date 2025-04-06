import sys
import signal
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from video_annotator import VideoAnnotator

def signal_handler(signum, frame):
    """处理终止信号"""
    # 获取应用实例
    app = QApplication.instance()
    if app is not None:
        # 使用计时器确保在主事件循环中退出
        QTimer.singleShot(0, app.quit)

def main():
    # 设置信号处理器
    signal.signal(signal.SIGINT, signal_handler)  # 处理 Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 处理终止信号
    
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle('Fusion')

    window = VideoAnnotator()
    window.show()
    
    # 允许信号在事件循环中被处理
    timer = QTimer()
    timer.start(500)  # 每500ms处理一次信号
    timer.timeout.connect(lambda: None)  # 空连接，仅用于处理信号
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 