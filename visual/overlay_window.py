from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QPolygonF


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
        self.raise_()

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

        # ── Observer: blue bounding boxes ────────────────────────────────────
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

        # ── Decider: yellow target highlight ─────────────────────────────────
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

        # ── Executor: action indicators ────────────────────────────────────────
        if self._ripple:
            alpha = self._ripple["alpha"]
            action_type = self._ripple.get("action_type", "click")

            if action_type == "scroll":
                self._draw_swipe_arrow(painter, alpha, self._ripple.get("scroll_direction", "up"))
            elif action_type in ("click", "long_click", "input"):
                self._draw_tap_indicator(painter, alpha, self._ripple["x"], self._ripple["y"])
            elif action_type == "press_back":
                self._draw_system_button(painter, alpha, "BACK", "bottom-left")
            elif action_type == "press_home":
                self._draw_system_button(painter, alpha, "HOME", "bottom-center")
            elif action_type == "press_enter":
                self._draw_system_button(painter, alpha, "ENTER", "bottom-right")

        painter.end()

    def _draw_tap_indicator(self, painter, alpha, phone_x, phone_y):
        """Precise single-pixel tap point with crosshair — exact coordinate."""
        rx, ry = self._map(phone_x, phone_y)
        color = QColor(255, 50, 50, alpha)

        # Center dot (precise tap point)
        dot_r = 4
        painter.setPen(QPen(color, 1))
        painter.setBrush(color)
        painter.drawEllipse(rx - dot_r, ry - dot_r, dot_r * 2, dot_r * 2)

        # Short crosshair for exactness
        gap = dot_r + 2
        arm = 14
        painter.setPen(QPen(color, 1))
        painter.drawLine(rx - gap - arm, ry, rx - gap, ry)
        painter.drawLine(rx + gap, ry, rx + gap + arm, ry)
        painter.drawLine(rx, ry - gap - arm, rx, ry - gap)
        painter.drawLine(rx, ry + gap, rx, ry + gap + arm)

    def _draw_swipe_arrow(self, painter, alpha, direction):
        """Swipe direction arrow centered on screen."""
        color = QColor(0, 220, 180, alpha)
        cx = self.width() // 2
        cy = self.height() // 2
        arrow_len = 80

        # Arrow shaft + head in direction
        if direction == "up":
            tip = QPointF(cx, cy - arrow_len)
            base = QPointF(cx, cy + arrow_len // 2)
        elif direction == "down":
            tip = QPointF(cx, cy + arrow_len)
            base = QPointF(cx, cy - arrow_len // 2)
        elif direction == "left":
            tip = QPointF(cx - arrow_len, cy)
            base = QPointF(cx + arrow_len // 2, cy)
        else:  # right
            tip = QPointF(cx + arrow_len, cy)
            base = QPointF(cx - arrow_len // 2, cy)

        # Shaft
        pen = QPen(color, 4)
        painter.setPen(pen)
        painter.drawLine(base.toPoint(), tip.toPoint())

        # Arrowhead triangle
        from math import pi, cos, sin
        arrow_deg = {"up": 270, "down": 90, "left": 180, "right": 0}.get(direction, 270)
        rad = arrow_deg * pi / 180
        size = 18
        p1 = QPointF(tip.x() + size * cos(rad), tip.y() + size * sin(rad))
        p2 = QPointF(tip.x() + size * cos(rad + 2.4), tip.y() + size * sin(rad + 2.4))
        p3 = QPointF(tip.x() + size * cos(rad - 2.4), tip.y() + size * sin(rad - 2.4))
        painter.setBrush(color)
        painter.setPen(QPen(color, 1))
        painter.drawPolygon(QPolygonF([tip, p1, p2, p3]))

        # Label
        from PyQt5.QtGui import QFont
        painter.setPen(QPen(color, 1))
        label_pos = base.toPoint()
        painter.drawText(label_pos.x() + 8, label_pos.y() + 4, direction.upper())

    def _draw_system_button(self, painter, alpha, label, corner):
        """System button press indicator at screen edge."""
        color = QColor(255, 160, 0, alpha)
        pen = QPen(color, 3)
        painter.setPen(pen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 40))
        from PyQt5.QtGui import QFont
        painter.setFont(QFont("Segoe UI", 14, 1))

        w, h = self.width(), self.height()
        bw, bh = 80, 40
        if corner == "bottom-left":
            rx, ry = 10, h - bh - 10
        elif corner == "bottom-center":
            rx, ry = (w - bw) // 2, h - bh - 10
        else:  # bottom-right
            rx, ry = w - bw - 10, h - bh - 10

        painter.drawRoundedRect(rx, ry, bw, bh, 6, 6)
        painter.drawText(rx + bw // 2 - 20, ry + bh // 2 + 5, label)
