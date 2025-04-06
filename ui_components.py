from PyQt5.QtWidgets import QLabel, QSizePolicy, QSlider, QStyle
from PyQt5.QtGui import QPainter, QFontMetrics
from PyQt5.QtCore import Qt

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