from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen


class OverlayWindow(QWidget):
    update_signal = pyqtSignal(list, dict, dict)
    sync_geometry_signal = pyqtSignal(int, int, int, int)

    def __init__(self, device_w: int, device_h: int):
        super().__init__()
        self.device_w = device_w
        self.device_h = device_h
        self._boxes = []
        self._target_box = {}
        self._ripple = {}

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.update_signal.connect(self._apply_update)
        self.sync_geometry_signal.connect(self._apply_geometry)

        self._ripple_timer = QTimer(self)
        self._ripple_timer.timeout.connect(self._fade_ripple)

    def _apply_update(self, boxes, target_box, ripple):
        self._boxes = boxes
        self._target_box = target_box
        self._ripple = ripple
        if ripple:
            self._ripple_timer.stop()
            self._ripple_timer.start(50)
        else:
            self._ripple_timer.stop()
        self.update()

    def _apply_geometry(self, x, y, w, h):
        self.setGeometry(x, y, w, h)

    def _fade_ripple(self):
        if not self._ripple:
            self._ripple_timer.stop()
            return
        self._ripple["alpha"] = max(0, self._ripple["alpha"] - 15)
        if self._ripple["alpha"] == 0:
            self._ripple = {}
            self._ripple_timer.stop()
        self.update()

    def _map(self, phone_x, phone_y):
        w, h = max(self.width(), 1), max(self.height(), 1)
        return (
            int(phone_x / self.device_w * w),
            int(phone_y / self.device_h * h),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Observer: blue bounding boxes
        pen = QPen(QColor(0, 120, 255, 200))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 120, 255, 30))
        for box in self._boxes:
            if len(box) != 4:
                continue
            x1, y1 = self._map(box[0], box[1])
            x2, y2 = self._map(box[2], box[3])
            painter.drawRect(x1, y1, x2 - x1, y2 - y1)

        # Decider: yellow target highlight
        if self._target_box:
            b = self._target_box.get("bounds", [])
            if len(b) == 4:
                x1, y1 = self._map(b[0], b[1])
                x2, y2 = self._map(b[2], b[3])
                pen = QPen(QColor(255, 200, 0, 230))
                pen.setWidth(3)
                painter.setPen(pen)
                painter.setBrush(QColor(255, 200, 0, 60))
                painter.drawRect(x1, y1, x2 - x1, y2 - y1)

        # Executor: red ripple circle
        if self._ripple:
            rx, ry = self._map(self._ripple["x"], self._ripple["y"])
            alpha = self._ripple["alpha"]
            pen = QPen(QColor(255, 50, 50, alpha))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.setBrush(QColor(255, 50, 50, alpha // 3))
            painter.drawEllipse(rx - 30, ry - 30, 60, 60)

        painter.end()
