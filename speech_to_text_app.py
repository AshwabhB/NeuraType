import sys
import math
import random
import os
import re
import threading
import keyboard

# IMPORTANT: Import backend BEFORE PyQt6 to avoid DLL conflicts.
from backend import (
    TranscriberBackend, WHISPER_MODELS, DEFAULT_MODEL, DEFAULT_HOTKEY,
    DEFAULT_CANCEL_HOTKEY, DEVICE, GPU_INFO, SUPPORTED_LANGUAGES,
    HAS_OPENAI, load_settings, save_settings, _BASE_DIR, _DATA_DIR,
    LOCAL_LLM_MODELS, DEFAULT_LOCAL_LLM_MODEL,
    is_first_boot, mark_first_boot_done,
    get_downloaded_whisper_models_standalone, get_downloaded_llm_models_standalone,
    debug_logger, DEBUG_LOG_FILE,
)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTextEdit, QCheckBox,
    QMessageBox, QScrollArea, QFrame, QGraphicsDropShadowEffect,
    QSizePolicy, QTabWidget, QSlider, QSpinBox, QDialog, QDialogButtonBox,
    QFileDialog, QSystemTrayIcon, QMenu, QProgressBar, QGroupBox,
    QGridLayout, QListWidget, QListWidgetItem, QSplitter, QSpacerItem,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject,
    QSize, QPoint, QRect,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
    QIcon, QClipboard, QPalette, QAction,
)


# =========================================================================
# Color themes (CHG002: remove blue, add light/dark toggle)
# =========================================================================

THEMES = {
    "dark": {
        "BG":            "#121212",
        "BG_CARD":       "#1e1e1e",
        "BG_INPUT":      "#2a2a2a",
        "BORDER":        "#333333",
        "TEXT_PRIMARY":  "#e4e4e7",
        "TEXT_SECONDARY":"#a1a1aa",
        "TEXT_DIM":      "#71717a",
        "ACCENT":        "#7c3aed",
        "ACCENT_HOVER":  "#6d28d9",
        "ACCENT_LIGHT":  "#a78bfa",
        "ACCENT_GLOW":   "#7c3aed40",
        "GREEN":         "#10b981",
        "AMBER":         "#f59e0b",
        "RED":           "#ef4444",
        "BUTTON_BG":     "#2a2a2a",
        "BUTTON_HOVER":  "#3a3a3a",
    },
    "light": {
        "BG":            "#fafafa",
        "BG_CARD":       "#ffffff",
        "BG_INPUT":      "#f4f4f5",
        "BORDER":        "#e4e4e7",
        "TEXT_PRIMARY":  "#18181b",
        "TEXT_SECONDARY":"#52525b",
        "TEXT_DIM":      "#a1a1aa",
        "ACCENT":        "#7c3aed",
        "ACCENT_HOVER":  "#6d28d9",
        "ACCENT_LIGHT":  "#a78bfa",
        "ACCENT_GLOW":   "#7c3aed30",
        "GREEN":         "#059669",
        "AMBER":         "#d97706",
        "RED":           "#dc2626",
        "BUTTON_BG":     "#e4e4e7",
        "BUTTON_HOVER":  "#d4d4d8",
    },
}

def _t(key, theme_name="dark"):
    return THEMES.get(theme_name, THEMES["dark"]).get(key, "#ff00ff")


def global_stylesheet(theme="dark"):
    t = THEMES.get(theme, THEMES["dark"])
    return f"""
    QMainWindow, QDialog {{
        background-color: {t["BG"]};
    }}
    QWidget {{
        color: {t["TEXT_PRIMARY"]};
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    }}
    QScrollArea {{
        border: none;
        background-color: {t["BG"]};
    }}
    QTabWidget::pane {{
        border: 1px solid {t["BORDER"]};
        border-radius: 8px;
        background: {t["BG_CARD"]};
    }}
    QTabBar::tab {{
        background: {t["BG_INPUT"]};
        color: {t["TEXT_SECONDARY"]};
        padding: 8px 18px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        margin-right: 2px;
        font-weight: 600;
        font-size: 12px;
    }}
    QTabBar::tab:selected {{
        background: {t["BG_CARD"]};
        color: {t["TEXT_PRIMARY"]};
        border-bottom: 2px solid {t["ACCENT"]};
    }}
    QTabBar::tab:hover {{
        color: {t["TEXT_PRIMARY"]};
    }}
    QFrame#card {{
        background-color: {t["BG_CARD"]};
        border: 1px solid {t["BORDER"]};
        border-radius: 14px;
    }}
    QPushButton {{
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
        font-weight: 600;
        font-size: 13px;
    }}
    QPushButton#accent {{
        background-color: {t["ACCENT"]};
        color: white;
    }}
    QPushButton#accent:hover {{
        background-color: {t["ACCENT_HOVER"]};
    }}
    QPushButton#accent:pressed {{
        background-color: #5b21b6;
    }}
    QPushButton#accent:disabled {{
        background-color: {t["BG_INPUT"]};
        color: {t["TEXT_DIM"]};
    }}
    QPushButton#secondary {{
        background-color: {t["BUTTON_BG"]};
        color: {t["TEXT_SECONDARY"]};
    }}
    QPushButton#secondary:hover {{
        background-color: {t["BUTTON_HOVER"]};
        color: {t["TEXT_PRIMARY"]};
    }}
    QPushButton#recordBtn {{
        background-color: {t["ACCENT"]};
        color: white;
        font-size: 15px;
        font-weight: 700;
        padding: 14px 44px;
        border-radius: 12px;
    }}
    QPushButton#recordBtn:hover {{
        background-color: {t["ACCENT_HOVER"]};
    }}
    QPushButton#recordBtn:disabled {{
        background-color: {t["BG_INPUT"]};
        color: {t["TEXT_DIM"]};
    }}
    QPushButton#stopBtn {{
        background-color: {t["RED"]};
        color: white;
        font-size: 15px;
        font-weight: 700;
        padding: 14px 44px;
        border-radius: 12px;
    }}
    QPushButton#stopBtn:hover {{
        background-color: #b91c1c;
    }}
    QLineEdit {{
        background-color: {t["BG_INPUT"]};
        border: 1px solid {t["BORDER"]};
        border-radius: 8px;
        padding: 8px 12px;
        color: {t["TEXT_PRIMARY"]};
        font-size: 13px;
        selection-background-color: {t["ACCENT"]};
    }}
    QLineEdit:focus {{
        border-color: {t["ACCENT"]};
    }}
    QComboBox {{
        background-color: {t["BG_INPUT"]};
        border: 1px solid {t["BORDER"]};
        border-radius: 8px;
        padding: 7px 32px 7px 12px;
        color: {t["TEXT_PRIMARY"]};
        font-size: 13px;
        min-width: 120px;
    }}
    QComboBox:focus {{
        border-color: {t["ACCENT"]};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 0px;
    }}
    QComboBox::down-arrow {{
        image: none;
        width: 0;
        height: 0;
    }}
    QComboBox QAbstractItemView {{
        background-color: {t["BG_CARD"]};
        border: 1px solid {t["BORDER"]};
        border-radius: 8px;
        selection-background-color: {t["ACCENT"]};
        color: {t["TEXT_PRIMARY"]};
        padding: 4px;
        outline: 0;
    }}
    QCheckBox {{
        spacing: 8px;
        font-size: 13px;
        color: {t["TEXT_SECONDARY"]};
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {t["BORDER"]};
        border-radius: 4px;
        background-color: {t["BG_INPUT"]};
    }}
    QCheckBox::indicator:checked {{
        background-color: {t["ACCENT"]};
        border-color: {t["ACCENT"]};
    }}
    QCheckBox::indicator:hover {{
        border-color: {t["ACCENT_LIGHT"]};
    }}
    QTextEdit {{
        background-color: {t["BG_INPUT"]};
        border: 1px solid {t["BORDER"]};
        border-radius: 10px;
        padding: 14px;
        color: {t["TEXT_PRIMARY"]};
        font-size: 14px;
        selection-background-color: {t["ACCENT"]};
    }}
    QTextEdit:focus {{
        border-color: {t["ACCENT"]};
    }}
    QGroupBox {{
        background-color: {t["BG_CARD"]};
        border: 1px solid {t["BORDER"]};
        border-radius: 10px;
        margin-top: 14px;
        padding-top: 18px;
        font-weight: 600;
        font-size: 13px;
        color: {t["TEXT_PRIMARY"]};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {t["BORDER"]};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {t["ACCENT"]};
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}
    QSlider::sub-page:horizontal {{
        background: {t["ACCENT"]};
        border-radius: 3px;
    }}
    QSpinBox {{
        background-color: {t["BG_INPUT"]};
        border: 1px solid {t["BORDER"]};
        border-radius: 6px;
        padding: 4px 8px;
        color: {t["TEXT_PRIMARY"]};
        font-size: 13px;
    }}
    QListWidget {{
        background-color: {t["BG_INPUT"]};
        border: 1px solid {t["BORDER"]};
        border-radius: 8px;
        color: {t["TEXT_PRIMARY"]};
        font-size: 13px;
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 6px;
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background-color: {t["ACCENT"]};
        color: white;
    }}
    QProgressBar {{
        background: {t["BORDER"]};
        border-radius: 4px;
        height: 8px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {t["ACCENT"]};
        border-radius: 4px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {t["BORDER"]};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t["TEXT_DIM"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    """


# =========================================================================
# Custom ComboBox with painted chevron
# =========================================================================
class StyledComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#71717a"))
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        ax = self.width() - 16
        ay = self.height() // 2
        s = 3
        p.drawLine(ax - s, ay - 2, ax, ay + 2)
        p.drawLine(ax, ay + 2, ax + s, ay - 2)
        p.end()


# =========================================================================
# Thread-safe signal bridge
# =========================================================================
class BackendSignals(QObject):
    status = pyqtSignal(str, str)
    model_loaded = pyqtSignal(str)
    model_load_failed = pyqtSignal(str)
    transcription_complete = pyqtSignal(str)
    transcription_error = pyqtSignal(str)
    hotkey_triggered = pyqtSignal()
    hold_release = pyqtSignal()          # CHG6-fix: dedicated stop for hold mode
    cancel_hotkey_triggered = pyqtSignal()
    predownload_progress = pyqtSignal(str, int, int)
    silence_detected = pyqtSignal()
    history_hotkey_triggered = pyqtSignal()
    repaste_hotkey_triggered = pyqtSignal()
    transcription_stats = pyqtSignal(float, int, int)


# =========================================================================
# Particle visualizer widget
# =========================================================================
class _Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'radius', 'base_radius', 'color',
                 'opacity', 'home_x', 'home_y', 'phase')

    def __init__(self, x, y, color, base_radius=3.0):
        self.x = x
        self.y = y
        self.home_x = x
        self.home_y = y
        self.vx = 0.0
        self.vy = 0.0
        self.radius = base_radius
        self.base_radius = base_radius
        self.color = color
        self.opacity = 0.7
        self.phase = random.random() * math.tau


# Particle palette — purple/violet spectrum (CHG002: no blue)
_PARTICLE_COLORS = [
    "#7c3aed", "#8b5cf6", "#a78bfa", "#c4b5fd",
    "#6d28d9", "#5b21b6", "#ddd6fe", "#9333ea",
    "#a855f7", "#c084fc", "#e9d5ff", "#4c1d95",
]


class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setMinimumWidth(400)
        self._level = 0.0
        self._active = False
        self._tick_count = 0
        self._colors = [QColor(c) for c in _PARTICLE_COLORS]
        self._particles = []
        self._init_particles()
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    @staticmethod
    def _center_biased(n, w, margin=0.075):
        positions = []
        for i in range(n):
            t = (i + 0.5) / n
            biased = 0.5 * (1.0 - math.cos(math.pi * t))
            positions.append(margin * w + biased * w * (1 - 2 * margin))
        return positions

    def _init_particles(self):
        self._particles.clear()
        w = max(self.width(), 400)
        h = self.height()
        n = 120
        for i, x in enumerate(self._center_biased(n, w)):
            y = h / 2 + random.uniform(-6, 6)
            cf = math.sin(math.pi * i / (n - 1))
            r = random.uniform(0.8, 2.0) + cf * 1.2
            self._particles.append(_Particle(x, y, random.choice(self._colors), r))

    def start(self):
        self._active = True
        self._tick_count = 0
        w, h = self.width(), self.height()
        for i, p in enumerate(self._particles):
            p.home_x = self._center_biased(len(self._particles), w)[i]
            p.home_y = h / 2
            p.x, p.y = p.home_x, p.home_y
            p.vx = p.vy = 0.0
        self._timer.start()

    def stop(self):
        self._active = False
        self._timer.stop()
        for p in self._particles:
            p.x, p.y = p.home_x, p.home_y
            p.vx = p.vy = 0.0
            p.radius = p.base_radius
            p.opacity = 0.3
        self.update()

    def set_level(self, level):
        self._level = level

    def _tick(self):
        self._tick_count += 1
        t = self._tick_count * 0.04
        level = self._level
        h = self.height()
        n = len(self._particles)
        for i, p in enumerate(self._particles):
            env = math.sin(math.pi * i / (n - 1))
            energy = level * env
            dy = (math.sin(t * 3.0 + p.phase) * energy * h * 0.38
                  + math.sin(t * 1.7 + p.phase * 2.3) * energy * h * 0.12)
            jx = random.uniform(-0.6, 0.6) * (0.3 + level * 0.7)
            jy = random.uniform(-0.6, 0.6) * (0.3 + level * 0.7)
            p.vx += (p.home_x - p.x) * 0.15 + jx
            p.vy += (p.home_y + dy - p.y) * 0.15 + jy
            p.vx *= 0.78
            p.vy *= 0.78
            p.x += p.vx
            p.y += p.vy
            p.radius = p.base_radius + energy * 1.8 + math.sin(t * 4 + p.phase) * energy * 0.8
            p.opacity = 0.4 + energy * 0.6
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self._particles:
            c = QColor(p.color)
            if not self._active:
                c = QColor("#333333")
                c.setAlphaF(0.4)
            else:
                c.setAlphaF(min(1.0, p.opacity))
            if self._active and p.opacity > 0.55 and p.radius > 1.8:
                glow = QColor(c)
                glow.setAlphaF(min(1.0, p.opacity * 0.2))
                painter.setBrush(QBrush(glow))
                gr = p.radius * 2.5
                painter.drawEllipse(int(p.x - gr / 2), int(p.y - gr / 2), int(gr), int(gr))
            painter.setBrush(QBrush(c))
            r = p.radius
            painter.drawEllipse(int(p.x - r / 2), int(p.y - r / 2), int(r), int(r))
        painter.end()


# =========================================================================
# Recording indicator — bottom center of active screen (CHG003 / CHG031)
# =========================================================================
class RecordingIndicator(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(80, 30)
        self._level = 0.0
        self._tick_count = 0
        self._colors = [QColor(c) for c in _PARTICLE_COLORS]
        self._particles = []
        self._init_particles()
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def _indicator_positions(self, n, w, pad=8):
        positions = []
        for i in range(n):
            t = (i + 0.5) / n
            biased = 0.5 * (1.0 - math.cos(math.pi * t))
            positions.append(pad + biased * (w - 2 * pad))
        return positions

    def _init_particles(self):
        self._particles.clear()
        w, h, n = self.width(), self.height(), 35
        for i, x in enumerate(self._indicator_positions(n, w)):
            cf = math.sin(math.pi * i / (n - 1))
            r = random.uniform(0.6, 1.5) + cf * 0.8
            self._particles.append(_Particle(x, h / 2, random.choice(self._colors), r))

    def set_level(self, level):
        self._level = level

    def show_indicator(self):
        # CHG003 / CHG031: position at bottom center of active screen
        geo = None
        try:
            info = TranscriberBackend.get_active_screen_geometry()
            if info:
                geo = info
        except Exception:
            pass
        if geo:
            cx = (geo["left"] + geo["right"]) // 2
            self.move(cx - self.width() // 2, geo["bottom"] - 60)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                g = screen.availableGeometry()
                self.move(g.center().x() - self.width() // 2, g.bottom() - 60)

        self._tick_count = 0
        w, h = self.width(), self.height()
        for i, p in enumerate(self._particles):
            pos = self._indicator_positions(len(self._particles), w)
            p.home_x = pos[i]
            p.home_y = h / 2
            p.x, p.y = p.home_x, p.home_y
            p.vx = p.vy = 0.0
        self._timer.start()
        self.show()

    def hide_indicator(self):
        self._timer.stop()
        for p in self._particles:
            p.x, p.y = p.home_x, p.home_y
        self.hide()

    def _tick(self):
        self._tick_count += 1
        t = self._tick_count * 0.04
        level = self._level
        h = self.height()
        n = len(self._particles)
        for i, p in enumerate(self._particles):
            env = math.sin(math.pi * i / (n - 1))
            energy = level * env
            dy = math.sin(t * 3.0 + p.phase) * energy * h * 0.35
            jy = random.uniform(-0.3, 0.3) * (0.3 + level * 0.7)
            p.vy += (p.home_y + dy - p.y) * 0.15 + jy
            p.vy *= 0.78
            p.y += p.vy
            p.radius = p.base_radius + energy * 1.2
            p.opacity = 0.45 + energy * 0.55
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Get theme
        t = THEMES.get(_current_theme, THEMES["dark"])
        p.setPen(QPen(QColor(t["BORDER"]), 1))
        p.setBrush(QBrush(QColor(t["BG_CARD"])))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self._particles:
            c = QColor(pt.color)
            c.setAlphaF(min(1.0, pt.opacity))
            if pt.opacity > 0.5:
                glow = QColor(c)
                glow.setAlphaF(min(1.0, pt.opacity * 0.3))
                p.setBrush(QBrush(glow))
                gr = pt.radius * 2.0
                p.drawEllipse(int(pt.x - gr / 2), int(pt.y - gr / 2), int(gr), int(gr))
            p.setBrush(QBrush(c))
            r = pt.radius
            p.drawEllipse(int(pt.x - r / 2), int(pt.y - r / 2), int(r), int(r))
        p.end()


# Global theme tracker
_current_theme = "dark"


def make_card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 18)
    layout.setSpacing(10)
    return frame, layout


# =========================================================================
# Settings window (CHG002: separate window for all settings)
# =========================================================================
class SettingsWindow(QDialog):
    settings_changed = pyqtSignal()
    _mic_level_signal = pyqtSignal(int)
    _api_validate_signal = pyqtSignal(str, str)  # text, color

    def __init__(self, parent, backend):
        super().__init__(parent)
        self.backend = backend
        self.setWindowTitle("NeuraType Settings")
        self.setMinimumSize(700, 600)
        self.resize(780, 650)
        self._build_ui()
        self._mic_level_signal.connect(self._mic_level_bar.setValue)
        self._api_validate_signal.connect(self._on_api_validated)
        self._load_values()
        self._update_ai_checkboxes()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_hotkeys_tab(), "Hotkeys")
        tabs.addTab(self._build_transcription_tab(), "Transcription")
        tabs.addTab(self._build_ai_tab(), "AI Features")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        tabs.addTab(self._build_dictionary_tab(), "Dictionary")
        tabs.addTab(self._build_snippets_tab(), "Snippets")
        tabs.addTab(self._build_models_tab(), "Models")
        lay.addWidget(tabs)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._save_and_close)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    # -- General tab --
    def _build_general_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        # Theme
        g = QGroupBox("Appearance")
        gl = QHBoxLayout(g)
        gl.addWidget(QLabel("Theme:"))
        self._theme_combo = StyledComboBox()
        self._theme_combo.addItems(["dark", "light"])
        gl.addWidget(self._theme_combo)
        gl.addStretch()
        lay.addWidget(g)

        # Model — only show models selected in the Models tab
        g2 = QGroupBox("Transcription Model")
        gl2 = QHBoxLayout(g2)
        gl2.addWidget(QLabel("Model:"))
        self._model_combo = StyledComboBox()
        selected_whisper = self.backend.settings.get(
            "selected_whisper_models", list(WHISPER_MODELS.keys())
        )
        for name in WHISPER_MODELS:
            if name in selected_whisper:
                self._model_combo.addItem(name)
        gl2.addWidget(self._model_combo)
        gl2.addStretch()
        lay.addWidget(g2)

        # Microphone
        g3 = QGroupBox("Microphone")
        gl3 = QVBoxLayout(g3)
        row = QHBoxLayout()
        row.addWidget(QLabel("Device:"))
        self._mic_combo = StyledComboBox()
        self._mic_combo.setMinimumWidth(260)
        row.addWidget(self._mic_combo)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self._refresh_mics)
        row.addWidget(refresh)
        self._check_mic_btn = QPushButton("Check Mic")
        self._check_mic_btn.setObjectName("accent")
        self._check_mic_btn.clicked.connect(self._check_mic)
        row.addWidget(self._check_mic_btn)
        row.addStretch()
        gl3.addLayout(row)
        self._mic_level_bar = QProgressBar()
        self._mic_level_bar.setRange(0, 100)
        self._mic_level_bar.setValue(0)
        self._mic_level_bar.setFixedHeight(12)
        self._mic_level_bar.setTextVisible(False)
        gl3.addWidget(self._mic_level_bar)
        lay.addWidget(g3)

        # System
        g4 = QGroupBox("System")
        gl4 = QVBoxLayout(g4)
        self._tray_cb = QCheckBox("Minimize to system tray")
        gl4.addWidget(self._tray_cb)
        self._autostart_cb = QCheckBox("Launch on Windows startup")
        gl4.addWidget(self._autostart_cb)
        self._stats_cb = QCheckBox("Show transcription stats")
        gl4.addWidget(self._stats_cb)
        self._audio_fb_cb = QCheckBox("Audio start/stop confirmation sounds")
        gl4.addWidget(self._audio_fb_cb)
        self._debug_cb = QCheckBox("Enable debug logging (saves to neuratype_debug.log)")
        gl4.addWidget(self._debug_cb)
        lay.addWidget(g4)

        lay.addStretch()
        return w

    # -- Hotkeys tab --
    def _build_hotkeys_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        g = QGroupBox("Hotkey Configuration")
        gl = QGridLayout(g)
        gl.setSpacing(10)

        gl.addWidget(QLabel("Start / Stop:"), 0, 0)
        self._hk_input = QLineEdit()
        gl.addWidget(self._hk_input, 0, 1)

        gl.addWidget(QLabel("Cancel:"), 1, 0)
        self._cancel_hk_input = QLineEdit()
        gl.addWidget(self._cancel_hk_input, 1, 1)

        gl.addWidget(QLabel("Re-paste:"), 2, 0)
        self._repaste_hk_input = QLineEdit()
        gl.addWidget(self._repaste_hk_input, 2, 1)

        gl.addWidget(QLabel("History:"), 3, 0)
        self._history_hk_input = QLineEdit()
        gl.addWidget(self._history_hk_input, 3, 1)

        lay.addWidget(g)

        g2 = QGroupBox("Hotkey Mode")
        gl2 = QHBoxLayout(g2)
        self._mode_combo = StyledComboBox()
        self._mode_combo.addItems(["toggle", "hold"])
        gl2.addWidget(QLabel("Mode:"))
        gl2.addWidget(self._mode_combo)
        gl2.addStretch()
        lay.addWidget(g2)

        opts = QGroupBox("Options")
        ol = QVBoxLayout(opts)
        self._hk_enabled_cb = QCheckBox("Enable global hotkey")
        ol.addWidget(self._hk_enabled_cb)
        self._auto_paste_cb = QCheckBox("Auto-paste transcription")
        ol.addWidget(self._auto_paste_cb)
        self._indicator_cb = QCheckBox("Show recording indicator")
        ol.addWidget(self._indicator_cb)
        lay.addWidget(opts)

        lay.addStretch()
        return w

    # -- Transcription tab --
    def _build_transcription_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        g = QGroupBox("Language")
        gl = QHBoxLayout(g)
        gl.addWidget(QLabel("Language:"))
        self._lang_combo = StyledComboBox()
        self._lang_combo.addItems(list(SUPPORTED_LANGUAGES.keys()))
        gl.addWidget(self._lang_combo)
        gl.addWidget(QLabel("Select \"Auto-Detect\" to let Whisper detect the language."))
        gl.addStretch()
        lay.addWidget(g)

        g2 = QGroupBox("Text Processing")
        gl2 = QVBoxLayout(g2)
        self._filler_cb = QCheckBox("Remove filler words (um, uh, like...)")
        gl2.addWidget(self._filler_cb)
        self._backtrack_cb = QCheckBox("Backtrack correction (\"scratch that\", \"no wait\"...)")
        gl2.addWidget(self._backtrack_cb)
        self._numlist_cb = QCheckBox("Auto-format numbered lists")
        gl2.addWidget(self._numlist_cb)
        self._smart_ins_cb = QCheckBox("Smart text insertion — adjust capitalization")
        gl2.addWidget(self._smart_ins_cb)
        lay.addWidget(g2)

        g3 = QGroupBox("Microphone Sensitivity")
        gl3 = QHBoxLayout(g3)
        gl3.addWidget(QLabel("Gain:"))
        self._sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self._sensitivity_slider.setRange(10, 300)
        self._sensitivity_slider.setValue(100)
        gl3.addWidget(self._sensitivity_slider)
        self._sensitivity_label = QLabel("1.0x")
        self._sensitivity_slider.valueChanged.connect(
            lambda v: self._sensitivity_label.setText(f"{v / 100:.1f}x")
        )
        gl3.addWidget(self._sensitivity_label)
        lay.addWidget(g3)

        g4 = QGroupBox("Recording")
        gl4 = QVBoxLayout(g4)
        self._silence_cb = QCheckBox("Auto-stop after silence")
        gl4.addWidget(self._silence_cb)
        row = QHBoxLayout()
        row.addWidget(QLabel("Silence timeout (s):"))
        self._silence_spin = QSpinBox()
        self._silence_spin.setRange(1, 30)
        self._silence_spin.setValue(3)
        row.addWidget(self._silence_spin)
        row.addStretch()
        gl4.addLayout(row)
        self._handsfree_cb = QCheckBox("Hands-free mode — continuous listening")
        gl4.addWidget(self._handsfree_cb)
        lay.addWidget(g4)

        lay.addStretch()
        return w

    # -- AI Features tab --
    def _build_ai_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        # --- AI Provider selection ---
        g = QGroupBox("AI Provider")
        gl = QVBoxLayout(g)

        # OpenAI row
        row = QHBoxLayout()
        row.addWidget(QLabel("OpenAI API Key:"))
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("sk-...")
        self._api_key_input.textChanged.connect(self._update_ai_checkboxes)
        row.addWidget(self._api_key_input)
        validate_btn = QPushButton("Validate")
        validate_btn.setObjectName("accent")
        validate_btn.clicked.connect(self._validate_api_key)
        row.addWidget(validate_btn)
        gl.addLayout(row)
        self._api_status_label = QLabel("")
        self._api_status_label.setStyleSheet("font-size: 11px;")
        gl.addWidget(self._api_status_label)
        if not HAS_OPENAI:
            warn = QLabel("Install the 'openai' package: pip install openai")
            warn.setStyleSheet("color: #f59e0b; font-size: 11px;")
            gl.addWidget(warn)

        # Local LLM row
        self._local_llm_cb = QCheckBox("Use local LLM (no internet, runs on GPU)")
        self._local_llm_cb.toggled.connect(self._update_ai_checkboxes)
        gl.addWidget(self._local_llm_cb)

        # Local LLM model selector — only show models selected in the Models tab
        llm_model_row = QHBoxLayout()
        llm_model_row.addWidget(QLabel("LLM Model:"))
        self._llm_model_combo = QComboBox()
        selected_llm = self.backend.settings.get("selected_llm_models", [])
        for name, info in LOCAL_LLM_MODELS.items():
            if name in selected_llm:
                self._llm_model_combo.addItem(f"{name}  ({info['size']})", name)
        self._llm_model_combo.currentIndexChanged.connect(self._update_ai_checkboxes)
        llm_model_row.addWidget(self._llm_model_combo, 1)
        gl.addLayout(llm_model_row)

        # Hint shown when no LLM models are available
        self._llm_no_models_hint = QLabel(
            "No LLM models selected. Go to Settings > Models tab to add one first."
        )
        self._llm_no_models_hint.setWordWrap(True)
        self._llm_no_models_hint.setStyleSheet("font-size: 11px; color: #f59e0b;")
        self._llm_no_models_hint.setVisible(self._llm_model_combo.count() == 0)
        gl.addWidget(self._llm_no_models_hint)

        self._llm_model_desc = QLabel("")
        self._llm_model_desc.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        gl.addWidget(self._llm_model_desc)

        self._llm_status_label = QLabel("")
        self._llm_status_label.setStyleSheet("font-size: 11px;")
        gl.addWidget(self._llm_status_label)

        note = QLabel(
            "Provide an OpenAI key OR enable local LLM to unlock the features below.\n"
            "If both are set, OpenAI takes priority. The selected LLM model "
            "downloads automatically on first use."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px;")
        gl.addWidget(note)
        lay.addWidget(g)

        g2 = QGroupBox("Text Enhancement")
        gl2 = QVBoxLayout(g2)
        self._grammar_cb = QCheckBox("Correct grammar and spelling")
        gl2.addWidget(self._grammar_cb)
        self._format_cb = QCheckBox("Auto-format (bullet points, lists)")
        gl2.addWidget(self._format_cb)
        lay.addWidget(g2)

        g3 = QGroupBox("Advanced AI")
        gl3 = QVBoxLayout(g3)
        self._command_cb = QCheckBox("Command mode — highlight text + speak to transform")
        gl3.addWidget(self._command_cb)
        self._tone_cb = QCheckBox("Context-aware tone matching")
        gl3.addWidget(self._tone_cb)
        lay.addWidget(g3)

        self._ai_checkboxes = [self._grammar_cb, self._format_cb, self._command_cb, self._tone_cb]

        lay.addStretch()
        return w

    # -- Advanced tab --
    def _build_advanced_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        g = QGroupBox("GPU Management")
        gl = QVBoxLayout(g)
        row = QHBoxLayout()
        row.addWidget(QLabel("Auto-release GPU after idle (minutes, 0=disabled):"))
        self._gpu_idle_spin = QSpinBox()
        self._gpu_idle_spin.setRange(0, 120)
        self._gpu_idle_spin.setValue(0)
        self._gpu_idle_spin.setSpecialValueText("Disabled")
        row.addWidget(self._gpu_idle_spin)
        row.addStretch()
        gl.addLayout(row)
        self._adaptive_cb = QCheckBox("Use fast model for short recordings < 3s")
        gl.addWidget(self._adaptive_cb)
        lay.addWidget(g)

        g2 = QGroupBox("Paste Settings")
        gl2 = QHBoxLayout(g2)
        gl2.addWidget(QLabel("Paste delay (ms):"))
        self._paste_delay_spin = QSpinBox()
        self._paste_delay_spin.setRange(50, 500)
        self._paste_delay_spin.setValue(100)
        self._paste_delay_spin.setSingleStep(25)
        gl2.addWidget(self._paste_delay_spin)
        gl2.addStretch()
        lay.addWidget(g2)

        lay.addStretch()
        return w

    # -- Dictionary tab (CHG005 / CHG017) --
    def _build_dictionary_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        g = QGroupBox("Custom Dictionary")
        gl = QVBoxLayout(g)
        gl.addWidget(QLabel("Allowed words (won't be auto-corrected):"))
        self._dict_list = QListWidget()
        gl.addWidget(self._dict_list)
        row = QHBoxLayout()
        self._dict_input = QLineEdit()
        self._dict_input.setPlaceholderText("Enter a word...")
        row.addWidget(self._dict_input)
        add_btn = QPushButton("Add")
        add_btn.setObjectName("accent")
        add_btn.clicked.connect(self._add_dict_word)
        row.addWidget(add_btn)
        rm_btn = QPushButton("Remove")
        rm_btn.setObjectName("secondary")
        rm_btn.clicked.connect(self._remove_dict_word)
        row.addWidget(rm_btn)
        gl.addLayout(row)
        lay.addWidget(g)

        g2 = QGroupBox("Learned Corrections")
        gl2 = QVBoxLayout(g2)
        gl2.addWidget(QLabel("Auto-learned word corrections:"))
        self._corrections_list = QListWidget()
        gl2.addWidget(self._corrections_list)
        rm2 = QPushButton("Remove Selected")
        rm2.setObjectName("secondary")
        rm2.clicked.connect(self._remove_correction)
        gl2.addWidget(rm2)
        lay.addWidget(g2)

        return w

    # -- Snippets tab (CHG016) --
    def _build_snippets_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        g = QGroupBox("Snippet Library")
        gl = QVBoxLayout(g)
        gl.addWidget(QLabel("Trigger phrases are replaced with snippet text during transcription."))
        self._snippet_list = QListWidget()
        gl.addWidget(self._snippet_list)
        row = QHBoxLayout()
        self._snip_trigger = QLineEdit()
        self._snip_trigger.setPlaceholderText("Trigger phrase...")
        row.addWidget(self._snip_trigger)
        self._snip_replace = QLineEdit()
        self._snip_replace.setPlaceholderText("Replacement text...")
        row.addWidget(self._snip_replace)
        add_btn = QPushButton("Add")
        add_btn.setObjectName("accent")
        add_btn.clicked.connect(self._add_snippet)
        row.addWidget(add_btn)
        rm_btn = QPushButton("Remove")
        rm_btn.setObjectName("secondary")
        rm_btn.clicked.connect(self._remove_snippet)
        row.addWidget(rm_btn)
        gl.addLayout(row)
        lay.addWidget(g)

        lay.addStretch()
        return w

    # -- Models tab --
    def _build_models_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)

        # --- Whisper Models ---
        g_whisper = QGroupBox("Voice Models (Whisper)")
        wl = QVBoxLayout(g_whisper)
        self._models_whisper_cbs = {}
        downloaded_whisper = self.backend.get_downloaded_whisper_models()
        selected_whisper = self.backend.settings.get(
            "selected_whisper_models", list(WHISPER_MODELS.keys())
        )
        for name, info in WHISPER_MODELS.items():
            is_dl = name in downloaded_whisper
            status = "  [Downloaded]" if is_dl else ""
            cb = QCheckBox(f"{name}  —  {info['size']}  ({info['desc']}){status}")
            cb.setChecked(name in selected_whisper)
            self._models_whisper_cbs[name] = cb
            wl.addWidget(cb)
        wl.addStretch()
        lay.addWidget(g_whisper)

        # --- LLM Models ---
        g_llm = QGroupBox("AI Text Models (LLM)")
        ll = QVBoxLayout(g_llm)
        self._models_llm_cbs = {}
        downloaded_llm = self.backend.get_downloaded_llm_models()
        selected_llm = self.backend.settings.get("selected_llm_models", [])
        for name, info in LOCAL_LLM_MODELS.items():
            is_dl = name in downloaded_llm
            status = "  [Downloaded]" if is_dl else ""
            cb = QCheckBox(f"{name}  —  {info['size']}  ({info['desc']}){status}")
            cb.setChecked(name in selected_llm)
            self._models_llm_cbs[name] = cb
            ll.addWidget(cb)
        ll.addStretch()
        lay.addWidget(g_llm)

        note = QLabel(
            "Checking a model will download it on save. Unchecking a downloaded model "
            "will delete its files from disk after confirmation."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        lay.addWidget(note)

        lay.addStretch()
        return w

    # -- Load values from settings --
    def _load_values(self):
        s = self.backend.settings
        self._theme_combo.setCurrentText(s.get("theme", "dark"))
        self._model_combo.setCurrentText(s.get("model", "turbo"))
        self._refresh_mics()
        saved_mic = s.get("mic_device_name")
        if saved_mic:
            for i in range(self._mic_combo.count()):
                if saved_mic in self._mic_combo.itemText(i):
                    self._mic_combo.setCurrentIndex(i)
                    break
        self._tray_cb.setChecked(s.get("minimize_to_tray", True))
        self._autostart_cb.setChecked(s.get("auto_start", False))
        self._stats_cb.setChecked(s.get("show_stats", True))
        self._audio_fb_cb.setChecked(s.get("audio_feedback", True))
        self._debug_cb.setChecked(s.get("debug_logging", False))
        self._hk_input.setText(s.get("hotkey", DEFAULT_HOTKEY))
        self._cancel_hk_input.setText(s.get("cancel_hotkey", DEFAULT_CANCEL_HOTKEY))
        self._repaste_hk_input.setText(s.get("repaste_hotkey", "alt+shift+z"))
        self._history_hk_input.setText(s.get("history_hotkey", "ctrl+shift+h"))
        self._mode_combo.setCurrentText(s.get("hotkey_mode", "toggle"))
        self._hk_enabled_cb.setChecked(s.get("hotkey_enabled", True))
        self._auto_paste_cb.setChecked(s.get("auto_paste", True))
        self._indicator_cb.setChecked(s.get("recording_indicator", True))
        # CHG8-fix migration: if legacy auto_detect_language is true, switch
        # the dropdown to "Auto-Detect" and clear the legacy key.
        lang = s.get("language", "English")
        if s.get("auto_detect_language", False) and lang != "Auto-Detect":
            lang = "Auto-Detect"
            s["language"] = lang
            s.pop("auto_detect_language", None)
        self._lang_combo.setCurrentText(lang)
        self._filler_cb.setChecked(s.get("filler_removal", False))
        self._backtrack_cb.setChecked(s.get("backtrack_correction", False))
        self._numlist_cb.setChecked(s.get("numbered_list_format", False))
        self._smart_ins_cb.setChecked(s.get("smart_insertion", False))
        self._sensitivity_slider.setValue(int(s.get("mic_sensitivity", 1.0) * 100))
        self._silence_cb.setChecked(s.get("silence_auto_stop", False))
        self._silence_spin.setValue(s.get("silence_timeout_seconds", 3))
        self._handsfree_cb.setChecked(s.get("hands_free_mode", False))
        self._api_key_input.setText(s.get("openai_api_key", ""))
        self._local_llm_cb.setChecked(s.get("use_local_llm", False))
        # Set LLM model combo
        llm_model = s.get("local_llm_model", DEFAULT_LOCAL_LLM_MODEL)
        idx = self._llm_model_combo.findData(llm_model)
        if idx >= 0:
            self._llm_model_combo.setCurrentIndex(idx)
        else:
            self._llm_model_combo.setCurrentIndex(0)
        self._grammar_cb.setChecked(s.get("correct_grammar", False))
        self._format_cb.setChecked(s.get("auto_format", False))
        self._command_cb.setChecked(s.get("command_mode", False))
        self._tone_cb.setChecked(s.get("context_aware_tone", False))
        self._gpu_idle_spin.setValue(s.get("gpu_idle_release_minutes", 0))
        self._adaptive_cb.setChecked(s.get("adaptive_model", False))
        self._paste_delay_spin.setValue(s.get("paste_delay_ms", 100))
        # Dictionary
        self._dict_list.clear()
        for w in self.backend.dictionary.get_allowed_words():
            self._dict_list.addItem(w)
        self._corrections_list.clear()
        for orig, corr in self.backend.dictionary.get_corrections().items():
            self._corrections_list.addItem(f"{orig} -> {corr}")
        # Snippets
        self._snippet_list.clear()
        for trigger, repl in self.backend.snippets.get_all().items():
            self._snippet_list.addItem(f'"{trigger}" -> "{repl}"')

    def _refresh_mics(self):
        self._mic_combo.clear()
        devices = TranscriberBackend.get_input_devices()
        self._mic_devices = devices
        for _, label in devices:
            self._mic_combo.addItem(label)
        if not devices:
            self._mic_combo.addItem("No microphones found")

    def _check_mic(self):
        # Toggle start/stop
        if getattr(self, '_mic_checking', False):
            self._mic_check_stop = True
            return

        self._mic_level_bar.setValue(0)
        self._mic_checking = True
        self._mic_check_stop = False
        self._check_mic_btn.setText("Stop Check")

        def on_level(l):
            self._mic_level_signal.emit(int(l * 100))

        def _run():
            try:
                import sounddevice as sd
                gain = self.backend.settings.get("mic_sensitivity", 1.0)
                import numpy as np
                stream = sd.InputStream(
                    device=self.backend.selected_device_index,
                    channels=1, samplerate=16000,
                )
                stream.start()
                while not self._mic_check_stop:
                    data, overflowed = stream.read(1600)  # 100ms chunks
                    rms = float(np.sqrt(np.mean((data * gain) ** 2)))
                    on_level(min(1.0, rms * 10))
                stream.stop()
                stream.close()
            except Exception as e:
                print(f"Mic check error: {e}")
            self._mic_level_signal.emit(0)
            self._mic_checking = False
            # Reset button text from main thread
            self._mic_level_signal.emit(-1)  # sentinel

        # Override signal to also reset button on -1
        old_handler = self._mic_level_bar.setValue

        def _handle_level(val):
            if val == -1:
                self._check_mic_btn.setText("Check Mic")
                self._mic_level_bar.setValue(0)
            else:
                self._mic_level_bar.setValue(val)

        try:
            self._mic_level_signal.disconnect()
        except Exception:
            pass
        self._mic_level_signal.connect(_handle_level)

        threading.Thread(target=_run, daemon=True).start()

    def _update_ai_checkboxes(self):
        """Enable/disable AI checkboxes based on API key or local LLM selection."""
        has_key = bool(self._api_key_input.text().strip())
        use_local = getattr(self, '_local_llm_cb', None) and self._local_llm_cb.isChecked()
        combo_empty = hasattr(self, '_llm_model_combo') and self._llm_model_combo.count() == 0

        # If user tries to enable local LLM but no models are selected, disable it
        has_ai = has_key or (use_local and not combo_empty)
        for cb in getattr(self, '_ai_checkboxes', []):
            cb.setEnabled(has_ai)
            if not has_ai:
                cb.setChecked(False)
        # Enable/disable model selector based on local LLM checkbox
        if hasattr(self, '_llm_model_combo'):
            self._llm_model_combo.setEnabled(use_local and not combo_empty)
        # Show/hide the "no models" hint
        if hasattr(self, '_llm_no_models_hint'):
            self._llm_no_models_hint.setVisible(use_local and combo_empty)
        # Update model description label
        if hasattr(self, '_llm_model_desc'):
            model_name = self._llm_model_combo.currentData() if hasattr(self, '_llm_model_combo') else None
            if model_name and use_local:
                info = LOCAL_LLM_MODELS.get(model_name, {})
                self._llm_model_desc.setText(info.get("desc", ""))
            else:
                self._llm_model_desc.setText("")
        # Update LLM status label
        if hasattr(self, '_llm_status_label') and use_local and not combo_empty:
            model_name = self._llm_model_combo.currentData() if hasattr(self, '_llm_model_combo') else None
            if model_name:
                info = LOCAL_LLM_MODELS.get(model_name, {})
                model_file = os.path.join(self.backend.model_dir, info.get("filename", ""))
                if os.path.exists(model_file):
                    self._llm_status_label.setText("Model ready.")
                    self._llm_status_label.setStyleSheet("color: #10b981; font-size: 11px;")
                else:
                    size = info.get("size", "")
                    self._llm_status_label.setText(f"Model will download on save ({size}).")
                    self._llm_status_label.setStyleSheet("color: #f59e0b; font-size: 11px;")
            else:
                self._llm_status_label.setText("")
        elif hasattr(self, '_llm_status_label'):
            self._llm_status_label.setText("")

    def _validate_api_key(self):
        key = self._api_key_input.text().strip()
        if not key:
            self._api_status_label.setText("Enter a key first.")
            self._api_status_label.setStyleSheet("color: #f59e0b; font-size: 11px;")
            return
        if not HAS_OPENAI:
            self._api_status_label.setText("openai package not installed.")
            self._api_status_label.setStyleSheet("color: #ef4444; font-size: 11px;")
            return
        self._api_status_label.setText("Validating...")
        self._api_status_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")

        def _run():
            try:
                from openai import OpenAI as _OAI
                client = _OAI(api_key=key)
                # Test with a real chat call (models.list works on free tier
                # but chat requires billing, so test both).
                client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=1,
                )
                self._api_validate_signal.emit("Valid key (billing OK)!", "#10b981")
            except Exception as e:
                err = str(e)
                if "insufficient_quota" in err or "billing" in err.lower():
                    self._api_validate_signal.emit(
                        "Key valid but no billing/credits — add payment at platform.openai.com",
                        "#ef4444",
                    )
                else:
                    self._api_validate_signal.emit(f"Invalid: {e}", "#ef4444")

        threading.Thread(target=_run, daemon=True).start()

    def _on_api_validated(self, text, color):
        self._api_status_label.setText(text)
        self._api_status_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    def _add_dict_word(self):
        word = self._dict_input.text().strip()
        if word:
            self.backend.dictionary.add_word(word)
            self._dict_list.addItem(word)
            self._dict_input.clear()

    def _remove_dict_word(self):
        item = self._dict_list.currentItem()
        if item:
            self.backend.dictionary.remove_word(item.text())
            self._dict_list.takeItem(self._dict_list.row(item))

    def _remove_correction(self):
        item = self._corrections_list.currentItem()
        if item:
            parts = item.text().split(" -> ")
            if parts:
                self.backend.dictionary.remove_word(parts[0].strip())
            self._corrections_list.takeItem(self._corrections_list.row(item))

    def _add_snippet(self):
        trigger = self._snip_trigger.text().strip()
        repl = self._snip_replace.text().strip()
        if trigger and repl:
            self.backend.snippets.add_snippet(trigger, repl)
            self._snippet_list.addItem(f'"{trigger}" -> "{repl}"')
            self._snip_trigger.clear()
            self._snip_replace.clear()

    def _remove_snippet(self):
        item = self._snippet_list.currentItem()
        if item:
            text = item.text()
            trigger = text.split('" -> "')[0].strip('"')
            self.backend.snippets.remove_snippet(trigger)
            self._snippet_list.takeItem(self._snippet_list.row(item))

    def _save_and_close(self):
        s = self.backend.settings
        s["theme"] = self._theme_combo.currentText()
        s["model"] = self._model_combo.currentText()
        # Mic
        idx = self._mic_combo.currentIndex()
        if hasattr(self, '_mic_devices') and 0 <= idx < len(self._mic_devices):
            s["mic_device_name"] = self._mic_combo.currentText()
            self.backend.selected_device_index = self._mic_devices[idx][0]
        s["minimize_to_tray"] = self._tray_cb.isChecked()
        s["auto_start"] = self._autostart_cb.isChecked()
        s["show_stats"] = self._stats_cb.isChecked()
        s["audio_feedback"] = self._audio_fb_cb.isChecked()
        s["debug_logging"] = self._debug_cb.isChecked()
        # Apply debug logging immediately
        debug_logger.set_enabled(s["debug_logging"])
        s["hotkey"] = self._hk_input.text().strip() or DEFAULT_HOTKEY
        s["cancel_hotkey"] = self._cancel_hk_input.text().strip() or DEFAULT_CANCEL_HOTKEY
        s["repaste_hotkey"] = self._repaste_hk_input.text().strip() or "alt+shift+z"
        s["history_hotkey"] = self._history_hk_input.text().strip() or "ctrl+shift+h"
        s["hotkey_mode"] = self._mode_combo.currentText()
        s["hotkey_enabled"] = self._hk_enabled_cb.isChecked()
        s["auto_paste"] = self._auto_paste_cb.isChecked()
        s["recording_indicator"] = self._indicator_cb.isChecked()
        s["language"] = self._lang_combo.currentText()
        s["filler_removal"] = self._filler_cb.isChecked()
        s["backtrack_correction"] = self._backtrack_cb.isChecked()
        s["numbered_list_format"] = self._numlist_cb.isChecked()
        s["smart_insertion"] = self._smart_ins_cb.isChecked()
        s["mic_sensitivity"] = self._sensitivity_slider.value() / 100.0
        s["silence_auto_stop"] = self._silence_cb.isChecked()
        s["silence_timeout_seconds"] = self._silence_spin.value()
        s["hands_free_mode"] = self._handsfree_cb.isChecked()
        s["openai_api_key"] = self._api_key_input.text().strip()
        # Only save use_local_llm=True if a model is actually available
        llm_combo_has_model = self._llm_model_combo.currentData() is not None
        s["use_local_llm"] = self._local_llm_cb.isChecked() and llm_combo_has_model
        s["local_llm_model"] = self._llm_model_combo.currentData() or DEFAULT_LOCAL_LLM_MODEL
        s["correct_grammar"] = self._grammar_cb.isChecked()
        s["auto_format"] = self._format_cb.isChecked()
        s["command_mode"] = self._command_cb.isChecked()
        s["context_aware_tone"] = self._tone_cb.isChecked()
        s["gpu_idle_release_minutes"] = self._gpu_idle_spin.value()
        s["adaptive_model"] = self._adaptive_cb.isChecked()
        s["paste_delay_ms"] = self._paste_delay_spin.value()

        # Apply auto-start
        TranscriberBackend.set_auto_start(s["auto_start"])

        # Update backend state
        self.backend.settings = s
        self.backend.auto_paste = s["auto_paste"]
        self.backend.hotkey_enabled = s["hotkey_enabled"]
        self.backend.openai_processor.set_api_key(s.get("openai_api_key", ""))

        # CHG7: trigger local LLM download/load if enabled
        selected_model = self._llm_model_combo.currentData()
        selected_llm_list = s.get("selected_llm_models", [])
        if s.get("use_local_llm", False) and selected_model and selected_model in selected_llm_list:
            llm = self.backend.local_llm
            # Switch model if user picked a different one (unloads old model)
            llm.set_model(selected_model)
            model_info = LOCAL_LLM_MODELS.get(selected_model, {})
            model_size = model_info.get("size", "")
            if not llm.is_model_downloaded:
                self.backend.on_status(
                    f"Downloading {selected_model} ({model_size})...", "#f59e0b"
                )
                llm.download_model(
                    on_progress=lambda dl, total: self.backend.on_status(
                        f"Downloading LLM: {dl / (1024**2):.0f} / {total / (1024**2):.0f} MB",
                        "#f59e0b",
                    ),
                    on_done=lambda: threading.Thread(
                        target=llm.load_model,
                        kwargs={"on_status": self.backend.on_status},
                        daemon=True,
                    ).start(),
                    on_error=lambda e: self.backend.on_status(f"LLM download failed: {e}", "#ef4444"),
                )
            elif not llm.is_loaded:
                self.backend.on_status(
                    f"Loading {selected_model}...", "#f59e0b"
                )
                threading.Thread(
                    target=llm.load_model,
                    kwargs={"on_status": self.backend.on_status},
                    daemon=True,
                ).start()

        # --- Models tab: handle selection changes ---
        if hasattr(self, '_models_whisper_cbs'):
            new_whisper = [n for n, cb in self._models_whisper_cbs.items() if cb.isChecked()]
            # Previous selection (what was checked before the user made changes)
            old_whisper = s.get("selected_whisper_models", list(WHISPER_MODELS.keys()))
            s["selected_whisper_models"] = new_whisper

            # Prevent unchecking the active model
            if self.backend.current_model_name not in new_whisper and new_whisper:
                s["model"] = new_whisper[0]
                self.backend.current_model_name = new_whisper[0]

            # Only prompt deletion for models explicitly unchecked by the user:
            # must have been in the OLD selection AND now removed AND downloaded on disk
            downloaded_whisper = self.backend.get_downloaded_whisper_models()
            explicitly_removed = [n for n in old_whisper if n not in new_whisper]
            for name in explicitly_removed:
                if name in downloaded_whisper and name != self.backend.current_model_name:
                    reply = QMessageBox.question(
                        self, "Delete Model",
                        f"Delete Whisper model '{name}' from disk?\n"
                        f"Size: {WHISPER_MODELS[name]['size']}",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.backend.delete_whisper_model(name)

            # Download newly checked whisper models in background
            needs_download = [n for n in new_whisper if n not in downloaded_whisper]
            if needs_download:
                self.backend.settings["selected_whisper_models"] = new_whisper
                self.backend.predownload_all_models()

        if hasattr(self, '_models_llm_cbs'):
            new_llm = [n for n, cb in self._models_llm_cbs.items() if cb.isChecked()]
            # Previous selection
            old_llm = s.get("selected_llm_models", [])
            s["selected_llm_models"] = new_llm

            # Only prompt deletion for models explicitly unchecked by the user
            downloaded_llm = self.backend.get_downloaded_llm_models()
            explicitly_removed_llm = [n for n in old_llm if n not in new_llm]
            for name in explicitly_removed_llm:
                if name in downloaded_llm:
                    reply = QMessageBox.question(
                        self, "Delete Model",
                        f"Delete LLM model '{name}' from disk?\n"
                        f"Size: {LOCAL_LLM_MODELS[name]['size']}",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.backend.delete_llm_model(name)

            # Download newly checked LLM models that aren't downloaded yet
            from backend import LocalLLMProcessor
            for name in new_llm:
                if name not in downloaded_llm:
                    llm_info = LOCAL_LLM_MODELS.get(name, {})
                    temp_llm = LocalLLMProcessor(
                        models_dir=self.backend.model_dir, model_name=name,
                    )
                    self.backend.on_status(
                        f"Downloading {name} ({llm_info.get('size', '')})...", "#f59e0b"
                    )
                    temp_llm.download_model(
                        on_progress=lambda dl, total, _n=name: self.backend.on_status(
                            f"Downloading {_n}: {dl / (1024**2):.0f} / {total / (1024**2):.0f} MB",
                            "#f59e0b",
                        ),
                        on_done=lambda _n=name: self.backend.on_status(
                            f"{_n} downloaded.", "#10b981"
                        ),
                        on_error=lambda e, _n=name: self.backend.on_status(
                            f"{_n} download failed: {e}", "#ef4444"
                        ),
                    )

        save_settings(s)

        self.settings_changed.emit()
        self.accept()


# =========================================================================
# Mic Check Dialog (CHG008)
# =========================================================================
class MicCheckDialog(QDialog):
    _level_signal = pyqtSignal(int)
    _result_signal = pyqtSignal(str, bool)  # status_text, enable_button

    def __init__(self, parent, backend):
        super().__init__(parent)
        self.backend = backend
        self.setWindowTitle("Microphone Check")
        self.setFixedSize(400, 200)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)

        lay.addWidget(QLabel("Speak into your microphone to test levels:"))
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(20)
        lay.addWidget(self._bar)

        self._status = QLabel("Click Start to begin...")
        lay.addWidget(self._status)

        row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.setObjectName("accent")
        self._start_btn.clicked.connect(self._start)
        row.addWidget(self._start_btn)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        lay.addLayout(row)

        self._level_signal.connect(self._bar.setValue)
        self._result_signal.connect(self._on_result)

    def _on_result(self, text, enable):
        self._status.setText(text)
        self._start_btn.setEnabled(enable)

    def _start(self):
        self._status.setText("Listening for 2 seconds...")
        self._start_btn.setEnabled(False)

        def on_level(l):
            self._level_signal.emit(int(l * 100))

        def _run():
            result = self.backend.check_mic(duration=2.0, on_level=on_level)
            if "error" in result:
                self._result_signal.emit(f"Error: {result['error']}", True)
            else:
                self._result_signal.emit(
                    f"Average: {result['average']:.4f}  |  Peak: {result['peak']:.4f}", True
                )

        threading.Thread(target=_run, daemon=True).start()


# =========================================================================
# First Boot Model Selection Dialog
# =========================================================================
class FirstBootDialog(QDialog):
    """Model selection dialog shown on first launch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NeuraType — First Boot Setup")
        self.setMinimumSize(650, 500)
        self.resize(700, 550)
        # Detect already-downloaded models (upgrade scenario)
        self._downloaded_whisper = get_downloaded_whisper_models_standalone()
        self._downloaded_llm = get_downloaded_llm_models_standalone()
        # Default selections: "turbo" + any already-downloaded models
        self._selected_whisper = list(set(["turbo"] + self._downloaded_whisper))
        self._selected_llm = list(self._downloaded_llm)
        self._build_ui()

    def _build_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(24, 24, 24, 24)
        main_lay.setSpacing(16)

        title = QLabel("Welcome to NeuraType!")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_lay.addWidget(title)

        desc = QLabel(
            "Select which models to download. Voice models handle speech recognition, "
            "LLM models handle grammar correction and text formatting.\n"
            "You can change this later in Settings > Models."
        )
        desc.setWordWrap(True)
        main_lay.addWidget(desc)

        # Two-column layout
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # --- Left column: Whisper voice models ---
        whisper_group = QGroupBox("Voice Models (Whisper)")
        whisper_lay = QVBoxLayout(whisper_group)
        self._whisper_cbs = {}
        for name, info in WHISPER_MODELS.items():
            is_dl = name in self._downloaded_whisper
            status = "  [Downloaded]" if is_dl else ""
            cb = QCheckBox(f"{name}  —  {info['size']}  ({info['desc']}){status}")
            # Pre-check: "turbo" always + any already downloaded models
            cb.setChecked(name == "turbo" or is_dl)
            self._whisper_cbs[name] = cb
            whisper_lay.addWidget(cb)
        whisper_lay.addStretch()
        columns.addWidget(whisper_group)

        # --- Right column: LLM models ---
        llm_group = QGroupBox("AI Text Models (LLM)")
        llm_lay = QVBoxLayout(llm_group)
        self._llm_cbs = {}
        for name, info in LOCAL_LLM_MODELS.items():
            is_dl = name in self._downloaded_llm
            status = "  [Downloaded]" if is_dl else ""
            cb = QCheckBox(f"{name}  —  {info['size']}  ({info['desc']}){status}")
            # Pre-check already downloaded LLMs
            cb.setChecked(is_dl)
            self._llm_cbs[name] = cb
            llm_lay.addWidget(cb)
        llm_lay.addStretch()
        columns.addWidget(llm_group)

        main_lay.addLayout(columns)

        save_btn = QPushButton("Save && Continue")
        save_btn.setObjectName("accent")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._on_save)
        main_lay.addWidget(save_btn)

    def _on_save(self):
        self._selected_whisper = [
            name for name, cb in self._whisper_cbs.items() if cb.isChecked()
        ]
        self._selected_llm = [
            name for name, cb in self._llm_cbs.items() if cb.isChecked()
        ]
        if not self._selected_whisper:
            QMessageBox.warning(
                self, "No Voice Model",
                "Please select at least one voice model (Whisper).",
            )
            return
        self.accept()

    def get_selections(self):
        return self._selected_whisper, self._selected_llm


# =========================================================================
# Main window (CHG000: NeuraType)
# =========================================================================
class NeuraTypeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeuraType")  # CHG000
        self.setMinimumSize(820, 700)
        self.resize(920, 780)

        icon_path = os.path.join(_BASE_DIR, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Signals bridge
        self._signals = BackendSignals()
        self._signals.status.connect(self._on_status)
        self._signals.model_loaded.connect(self._on_model_loaded)
        self._signals.model_load_failed.connect(self._on_model_load_failed)
        self._signals.transcription_complete.connect(self._on_transcription_complete)
        self._signals.transcription_error.connect(self._on_transcription_error)
        self._signals.hotkey_triggered.connect(self._toggle_recording)
        self._signals.hold_release.connect(self._on_hold_release)
        self._signals.cancel_hotkey_triggered.connect(self._cancel_recording)
        self._signals.predownload_progress.connect(self._on_predownload_progress)
        self._signals.silence_detected.connect(self._on_silence_detected)
        self._signals.history_hotkey_triggered.connect(self._show_history)
        self._signals.repaste_hotkey_triggered.connect(self._repaste)
        self._signals.transcription_stats.connect(self._on_stats)

        # Initialize tray early so _on_status callbacks during backend init don't crash
        self._tray = None

        # Recording indicator
        self._indicator = RecordingIndicator()
        self._indicator_enabled = True

        # Waveform poll timer
        self._waveform_timer = QTimer(self)
        self._waveform_timer.setInterval(40)
        self._waveform_timer.timeout.connect(self._poll_audio_level)

        self._build_ui()

        # Backend
        self.backend = TranscriberBackend(
            on_status=lambda t, c: self._signals.status.emit(t, c),
            on_model_loaded=lambda n: self._signals.model_loaded.emit(n),
            on_model_load_failed=lambda e: self._signals.model_load_failed.emit(e),
            on_transcription_complete=lambda t: self._signals.transcription_complete.emit(t),
            on_transcription_error=lambda e: self._signals.transcription_error.emit(e),
            on_hotkey_triggered=lambda: self._signals.hotkey_triggered.emit(),
            on_hold_release=lambda: self._signals.hold_release.emit(),
            on_cancel_hotkey_triggered=lambda: self._signals.cancel_hotkey_triggered.emit(),
            on_predownload_progress=lambda n, i, t: self._signals.predownload_progress.emit(n, i, t),
            on_silence_detected=lambda: self._signals.silence_detected.emit(),
            on_history_hotkey_triggered=lambda: self._signals.history_hotkey_triggered.emit(),
            on_repaste_hotkey_triggered=lambda: self._signals.repaste_hotkey_triggered.emit(),
            on_transcription_stats=lambda t, w, tw: self._signals.transcription_stats.emit(t, w, tw),
        )

        # Apply saved settings to UI
        self._apply_saved_settings()
        self._refresh_mic_list()
        self._apply_saved_mic()

        # Register hotkeys — clean slate to avoid stale hooks
        keyboard.unhook_all()
        self.backend._reregister_all_hotkeys()
        self._hotkey_label.setText(f"Hotkey active: {self.backend.current_hotkey}")
        self._hotkey_label.setStyleSheet(f"color: #10b981; font-size: 11px;")
        self.backend.start_hotkey_watchdog()

        # Load model — ensure active model is in the selected list
        selected_whisper = self.backend.settings.get(
            "selected_whisper_models", list(WHISPER_MODELS.keys())
        )
        if self.backend.current_model_name not in selected_whisper and selected_whisper:
            self.backend.current_model_name = selected_whisper[0]
            self.backend.settings["model"] = selected_whisper[0]

        self.backend.load_model(self.backend.current_model_name)
        self.backend.predownload_all_models()

        # CHG7: load local LLM at startup if enabled, selected, and downloaded
        selected_llm = self.backend.settings.get("selected_llm_models", [])
        if self.backend.settings.get("use_local_llm", False):
            llm = self.backend.local_llm
            saved_model = self.backend.settings.get("local_llm_model", DEFAULT_LOCAL_LLM_MODEL)
            if saved_model in selected_llm:
                llm.set_model(saved_model)
                if llm.is_model_downloaded and not llm.is_loaded:
                    threading.Thread(
                        target=llm.load_model,
                        kwargs={"on_status": self.backend.on_status},
                        daemon=True,
                    ).start()
                elif not llm.is_model_downloaded:
                    # Download if selected but not yet on disk
                    llm_info = LOCAL_LLM_MODELS.get(saved_model, {})
                    self.backend.on_status(
                        f"Downloading {saved_model} ({llm_info.get('size', '')})...", "#f59e0b"
                    )
                    llm.download_model(
                        on_progress=lambda dl, total: self.backend.on_status(
                            f"Downloading LLM: {dl / (1024**2):.0f} / {total / (1024**2):.0f} MB",
                            "#f59e0b",
                        ),
                        on_done=lambda: threading.Thread(
                            target=llm.load_model,
                            kwargs={"on_status": self.backend.on_status},
                            daemon=True,
                        ).start(),
                        on_error=lambda e: self.backend.on_status(
                            f"LLM download failed: {e}", "#ef4444"
                        ),
                    )

        # System tray (CHG023)
        self._setup_tray()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(36, 28, 36, 28)
        self._main_layout.setSpacing(18)

        self._build_header()
        self._build_record_card()
        self._build_transcription_card()
        self._build_stats_bar()

        scroll.setWidget(container)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _build_header(self):
        header = QHBoxLayout()

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel("NeuraType")  # CHG000
        title.setIndent(7)
        title.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        title_col.addWidget(title)

        subtitle = QLabel("by Ashwabh")
        subtitle.setIndent(7)
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet(f"color: {_t('TEXT_DIM')};")
        title_col.addWidget(subtitle)

        device_tag = "GPU" if DEVICE == "cuda" else "CPU"
        gpu_color = _t("GREEN") if DEVICE == "cuda" else _t("AMBER")
        gpu_label = QLabel(f"  {device_tag}: {GPU_INFO}")
        gpu_label.setFont(QFont("Segoe UI", 11))
        gpu_label.setStyleSheet(f"color: {gpu_color};")
        title_col.addWidget(gpu_label)

        self._hotkey_label = QLabel("")
        self._hotkey_label.setFont(QFont("Segoe UI", 10))
        title_col.addWidget(self._hotkey_label)

        header.addLayout(title_col)
        header.addStretch()

        right = QVBoxLayout()
        right.setSpacing(4)

        self._status_label = QLabel("Initializing...")
        self._status_label.setFont(QFont("Segoe UI", 12))
        self._status_label.setStyleSheet(f"color: {_t('TEXT_SECONDARY')};")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._status_label)

        self._model_info_label = QLabel("")
        self._model_info_label.setFont(QFont("Segoe UI", 10))
        self._model_info_label.setStyleSheet(f"color: {_t('TEXT_DIM')};")
        self._model_info_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._model_info_label)

        # Header buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._file_btn = QPushButton("Transcribe File")
        self._file_btn.setObjectName("secondary")
        self._file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._file_btn.setEnabled(False)  # enabled once model loads
        self._file_btn.clicked.connect(self._transcribe_from_file)
        btn_row.addWidget(self._file_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("secondary")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._open_settings)
        btn_row.addWidget(settings_btn)

        self._gpu_btn = QPushButton("Release GPU")
        self._gpu_btn.setObjectName("secondary")
        self._gpu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gpu_btn.clicked.connect(self._release_gpu)
        btn_row.addWidget(self._gpu_btn)
        right.addLayout(btn_row)

        header.addLayout(right)
        self._main_layout.addLayout(header)

    def _build_record_card(self):
        card, lay = make_card()
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._record_btn = QPushButton("Start Recording")
        self._record_btn.setObjectName("recordBtn")
        self._record_btn.setEnabled(False)
        self._record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._record_btn.clicked.connect(self._toggle_recording)

        idle_glow = QGraphicsDropShadowEffect(self._record_btn)
        idle_glow.setBlurRadius(20)
        idle_glow.setColor(QColor(_t("ACCENT_GLOW")))
        idle_glow.setOffset(0, 0)
        self._record_btn.setGraphicsEffect(idle_glow)

        btn_row.addStretch()
        btn_row.addWidget(self._record_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        t = THEMES.get(_current_theme, THEMES["dark"])
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background-color: {t['BUTTON_BG']}; color: {t['TEXT_SECONDARY']}; "
            f"font-size: 13px; font-weight: 600; padding: 10px 22px; border-radius: 10px; border: 1px solid {t['BORDER']}; }}"
            f"QPushButton:hover {{ background-color: {t['BUTTON_HOVER']}; color: {t['TEXT_PRIMARY']}; border-color: {t['RED']}; }}"
        )
        self._cancel_btn.clicked.connect(self._cancel_recording)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()

        lay.addLayout(btn_row)

        self._waveform = WaveformWidget()
        lay.addWidget(self._waveform, alignment=Qt.AlignmentFlag.AlignCenter)

        self._main_layout.addWidget(card)

    def _build_transcription_card(self):
        card, lay = make_card()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        header = QHBoxLayout()
        tt = QLabel("Transcription")
        tt.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        header.addWidget(tt)
        header.addStretch()

        # CHG001: copy only selected text
        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setObjectName("accent")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        header.addWidget(self._copy_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("secondary")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_text)
        header.addWidget(clear_btn)

        # CHG009: retry button
        self._retry_btn = QPushButton("Retry")
        self._retry_btn.setObjectName("secondary")
        self._retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(self._retry_transcription)
        header.addWidget(self._retry_btn)

        history_btn = QPushButton("History")
        history_btn.setObjectName("secondary")
        history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        history_btn.clicked.connect(self._show_history)
        header.addWidget(history_btn)

        lay.addLayout(header)

        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("Your transcriptions will appear here...")
        self._text_edit.setMinimumHeight(140)
        lay.addWidget(self._text_edit)

        self._main_layout.addWidget(card, stretch=1)

    def _build_stats_bar(self):
        """Transcription stats display (CHG028)."""
        self._stats_label = QLabel("")
        self._stats_label.setFont(QFont("Segoe UI", 10))
        self._stats_label.setStyleSheet(f"color: {_t('TEXT_DIM')};")
        self._stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(self._stats_label)

    # ------------------------------------------------------------------
    # System tray (CHG023)
    # ------------------------------------------------------------------
    def _setup_tray(self):
        self._tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon_path = os.path.join(_BASE_DIR, "icon.ico")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("NeuraType")

        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self._tray_show)
        menu.addAction(show_action)
        history_action = QAction("History", self)
        history_action.triggered.connect(self._show_history)
        menu.addAction(history_action)
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)
        refresh_hk_action = QAction("Refresh Hotkeys", self)
        refresh_hk_action.triggered.connect(self._refresh_hotkeys)
        menu.addAction(refresh_hk_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _tray_show(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show()

    def _refresh_hotkeys(self):
        """Manually re-register all hotkeys (tray menu action)."""
        debug_logger.log("_refresh_hotkeys: resetting listener...")
        try:
            # Clear ALL keyboard library state — both functions are needed
            keyboard.unhook_all()
            keyboard.unhook_all_hotkeys()
            listener = getattr(keyboard, '_listener', None)
            if listener is not None:
                # Reset listener state so start_if_necessary() recreates threads
                # and re-installs the Windows hook
                listener.listening = False
                # Reset internal hotkey state dicts so old combos can't fire
                for attr in ('blocking_hotkeys', 'nonblocking_hotkeys',
                             'blocking_keys', 'nonblocking_keys',
                             'filtered_modifiers', 'modifier_states'):
                    d = getattr(listener, attr, None)
                    if d is not None:
                        try:
                            d.clear()
                        except Exception:
                            pass
                if hasattr(listener, 'handlers'):
                    listener.handlers.clear()
            debug_logger.log("_refresh_hotkeys: listener reset OK")
        except Exception as e:
            debug_logger.log(f"_refresh_hotkeys: reset FAILED: {e}")
        self.backend._reregister_all_hotkeys()
        self._on_status("Hotkeys refreshed", "#10b981")

    def _quit_app(self):
        self._indicator.hide_indicator()
        self._save_settings()
        self.backend.cleanup()
        QApplication.quit()

    # ------------------------------------------------------------------
    # Backend callbacks
    # ------------------------------------------------------------------
    def _on_status(self, text, color):
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        if self._tray:
            self._tray.setToolTip(f"NeuraType — {text}")

    def _on_model_loaded(self, model_name):
        self._record_btn.setEnabled(True)
        self._file_btn.setEnabled(True)
        device_tag = "GPU" if DEVICE == "cuda" else "CPU"
        self._status_label.setText(f"Ready — '{model_name}' on {device_tag}")
        self._status_label.setStyleSheet(f"color: {_t('GREEN')}; font-size: 12px;")
        info = WHISPER_MODELS[model_name]
        self._model_info_label.setText(f"{info['desc']}  ·  {info['size']}")

    def _on_model_load_failed(self, error):
        self._record_btn.setEnabled(True)
        self._status_label.setText(f"Model load failed: {error}")
        self._status_label.setStyleSheet(f"color: {_t('RED')}; font-size: 12px;")

    def _on_predownload_progress(self, name, idx, total):
        self._status_label.setText(f"Pre-downloading '{name}' ({idx}/{total})...")
        self._status_label.setStyleSheet(f"color: {_t('AMBER')}; font-size: 12px;")

    def _on_transcription_complete(self, text):
        self._file_btn.setEnabled(True)
        self._record_btn.setEnabled(True)
        self._retry_btn.setVisible(False)
        if not text:
            self._status_label.setText("No speech detected")
            self._status_label.setStyleSheet(f"color: {_t('AMBER')}; font-size: 12px;")
            self._retry_btn.setVisible(True)
            return
        current = self._text_edit.toPlainText().strip()
        if current:
            self._text_edit.append("\n" + text)
        else:
            self._text_edit.setPlainText(text)
        device_tag = "GPU" if DEVICE == "cuda" else "CPU"
        self._status_label.setText(f"Ready — '{self.backend.current_model_name}' on {device_tag}")
        self._status_label.setStyleSheet(f"color: {_t('GREEN')}; font-size: 12px;")

    def _on_transcription_error(self, error):
        self._file_btn.setEnabled(True)
        self._record_btn.setEnabled(True)
        self._retry_btn.setVisible(True)  # CHG009
        QMessageBox.critical(self, "Transcription Error", f"Failed to transcribe:\n{error}")
        self._status_label.setText("Transcription failed")
        self._status_label.setStyleSheet(f"color: {_t('RED')}; font-size: 12px;")

    def _on_hold_release(self):
        """Stop recording when hold-mode key is released (CHG6-fix)."""
        if self.backend.is_recording:
            self._stop_recording()

    def _on_silence_detected(self):
        """Auto-stop on silence (CHG026)."""
        if self.backend.is_recording:
            self._stop_recording()

    def _on_stats(self, elapsed, word_count, total_words):
        """Update stats display (CHG028)."""
        if self.backend.settings.get("show_stats", True):
            session = self.backend.stats.get_session()
            self._stats_label.setText(
                f"Last: {elapsed:.1f}s, {word_count} words  |  "
                f"Session: {session['words']} words, {session['transcriptions']} transcriptions  |  "
                f"All time: {total_words} words"
            )

    def _repaste(self):
        """Re-paste last transcription (CHG020)."""
        self.backend.repaste_last()

    def _retry_transcription(self):
        """Retry last transcription (CHG009)."""
        if self.backend.retry_transcription():
            self._retry_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Mic
    # ------------------------------------------------------------------
    def _refresh_mic_list(self):
        devices = TranscriberBackend.get_input_devices()
        self._mic_devices = devices
        if hasattr(self, 'backend') and devices:
            default_name = TranscriberBackend.get_default_input_device_name()
            for j, (dev_i, label) in enumerate(devices):
                if default_name and default_name in label:
                    self.backend.selected_device_index = dev_i
                    break
            else:
                if devices:
                    self.backend.selected_device_index = devices[0][0]

    def _apply_saved_mic(self):
        saved_name = self.backend.settings.get("mic_device_name")
        if not saved_name or not hasattr(self, '_mic_devices'):
            return
        for j, (dev_i, label) in enumerate(self._mic_devices):
            if saved_name in label:
                self.backend.selected_device_index = dev_i
                break

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _open_settings(self):
        dlg = SettingsWindow(self, self.backend)
        dlg.setStyleSheet(global_stylesheet(_current_theme))
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _on_settings_changed(self):
        global _current_theme
        s = self.backend.settings
        new_theme = s.get("theme", "dark")
        if new_theme != _current_theme:
            _current_theme = new_theme
            app = QApplication.instance()
            # CHG2-fix: clear stylesheet first to bust Qt's style cache,
            # then reapply.  Without the clear, QFrame#card backgrounds
            # stay stale after a theme switch.
            app.setStyleSheet("")
            QApplication.processEvents()
            app.setStyleSheet(global_stylesheet(_current_theme))
            self._apply_theme_palette()
            # Force every child widget to re-evaluate its style
            for w in self.findChildren(QWidget):
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()

        # Update model if changed
        if s.get("model") != self.backend.current_model_name:
            self._record_btn.setEnabled(False)
            self.backend.load_model(s["model"])

        # Update indicator setting
        self._indicator_enabled = s.get("recording_indicator", True)
        if not self._indicator_enabled:
            self._indicator.hide_indicator()

        # Update hotkeys if changed
        if s.get("hotkey") != self.backend.current_hotkey:
            self.backend.unregister_hotkey()
            self.backend.current_hotkey = s["hotkey"]
            ok, text, color = self.backend.register_hotkey()
            self._hotkey_label.setText(text)
            self._hotkey_label.setStyleSheet(f"color: {color}; font-size: 11px;")

        if s.get("cancel_hotkey") != self.backend.current_cancel_hotkey:
            self.backend.unregister_cancel_hotkey()
            self.backend.current_cancel_hotkey = s["cancel_hotkey"]
            self.backend.register_cancel_hotkey()

        # Re-register extra hotkeys
        self.backend.unregister_repaste_hotkey()
        self.backend.register_repaste_hotkey()
        self.backend.unregister_history_hotkey()
        self.backend.register_history_hotkey()

    def _release_gpu(self):
        if self.backend.is_recording:
            QMessageBox.warning(self, "Recording", "Cannot release GPU while recording.")
            return
        # Toggle: Release ↔ Reload
        if self.backend._gpu_released or self.backend.whisper_model is None:
            self.backend.reload_model()
            self._gpu_btn.setText("Release GPU")
        else:
            self.backend.unload_model()
            self._gpu_btn.setText("Reload Model")
        # Never disable record — _start_recording handles missing model

    def _apply_saved_settings(self):
        s = self.backend.settings
        global _current_theme
        _current_theme = s.get("theme", "dark")
        self._indicator_enabled = s.get("recording_indicator", True)

    def _save_settings(self):
        save_settings(self.backend.settings)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def _toggle_recording(self):
        if getattr(self, '_recording_busy', False):
            return
        self._recording_busy = True
        QTimer.singleShot(300, lambda: setattr(self, '_recording_busy', False))

        if self.backend.model_loading:
            QMessageBox.warning(self, "Model Loading",
                                "Please wait for the model to load before recording.")
            return

        if not self.backend.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        # CHG1-fix: if model is unloaded, trigger async reload instead of blocking
        if self.backend._gpu_released or self.backend.whisper_model is None:
            if not self.backend.model_loading:
                self.backend.reload_model()
                self._gpu_btn.setText("Release GPU")
            self._status_label.setText("Model is reloading — try again in a moment")
            self._status_label.setStyleSheet(f"color: {_t('AMBER')}; font-size: 12px;")
            return

        try:
            self.backend.start_recording()
        except Exception as e:
            QMessageBox.critical(self, "Recording Error", f"Failed to start recording:\n{e}")
            return

        self._record_btn.setText("Stop Recording")
        self._record_btn.setObjectName("stopBtn")
        self._record_btn.setStyle(self._record_btn.style())
        self._start_btn_glow()
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setVisible(True)
        self._file_btn.setEnabled(False)
        self._waveform.start()
        if self._indicator_enabled:
            self._indicator.show_indicator()
        self._waveform_timer.start()

    def _stop_recording(self):
        self._reset_record_btn()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        self._indicator.hide_indicator()
        self._waveform.stop()
        self._waveform_timer.stop()
        self.backend.stop_recording()

    def _cancel_recording(self):
        if not self.backend.is_recording:
            return
        self._reset_record_btn()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        self._file_btn.setEnabled(True)
        self._indicator.hide_indicator()
        self._waveform.stop()
        self._waveform_timer.stop()
        self.backend.cancel_recording()
        device_tag = "GPU" if DEVICE == "cuda" else "CPU"
        self._status_label.setText(f"Recording cancelled — '{self.backend.current_model_name}' on {device_tag}")
        self._status_label.setStyleSheet(f"color: {_t('AMBER')}; font-size: 12px;")

    def _transcribe_from_file(self):
        """Open a file dialog and transcribe the selected audio/video file."""
        # Reload model if GPU was released
        if self.backend._gpu_released or self.backend.whisper_model is None:
            if not self.backend.model_loading:
                self.backend.reload_model()
                self._gpu_btn.setText("Release GPU")
            self._status_label.setText("Model is reloading — try again in a moment")
            self._status_label.setStyleSheet(f"color: {_t('AMBER')}; font-size: 12px;")
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.mp4 *.flac *.ogg *.webm *.wma *.aac *.mkv *.avi *.mov);;All Files (*)",
        )
        if not path:
            return
        self._file_btn.setEnabled(False)
        self._record_btn.setEnabled(False)
        threading.Thread(
            target=self.backend.transcribe_file, args=(path,), daemon=True
        ).start()

    def _reset_record_btn(self):
        self._record_btn.setText("Start Recording")
        self._record_btn.setObjectName("recordBtn")
        self._record_btn.setStyle(self._record_btn.style())
        self._stop_btn_glow()

    def _start_btn_glow(self):
        glow = QGraphicsDropShadowEffect(self._record_btn)
        glow.setBlurRadius(30)
        glow.setColor(QColor(_t("RED")))
        glow.setOffset(0, 0)
        self._record_btn.setGraphicsEffect(glow)
        self._glow_anim = QPropertyAnimation(glow, b"blurRadius")
        self._glow_anim.setDuration(800)
        self._glow_anim.setStartValue(15)
        self._glow_anim.setEndValue(40)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._glow_anim.setLoopCount(-1)
        self._glow_anim.start()

    def _stop_btn_glow(self):
        if hasattr(self, '_glow_anim'):
            self._glow_anim.stop()
        self._record_btn.setGraphicsEffect(None)

    def _poll_audio_level(self):
        if hasattr(self, 'backend') and self.backend.is_recording:
            level = self.backend.audio_level
            self._waveform.set_level(level)
            self._indicator.set_level(level)

    # ------------------------------------------------------------------
    # Text actions
    # ------------------------------------------------------------------
    def _clear_text(self):
        self._text_edit.clear()

    def _copy_to_clipboard(self):
        """CHG001: Copy only selected text. If nothing selected, copy all."""
        cursor = self._text_edit.textCursor()
        selected = cursor.selectedText().strip()
        if selected:
            text = selected
        else:
            text = self._text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "No Text", "There's no text to copy!")
            return
        QApplication.clipboard().setText(text)
        orig = self._copy_btn.text()
        self._copy_btn.setText("Copied!")
        self._copy_btn.setStyleSheet(
            f"background-color: {_t('GREEN')}; color: white; border: none; "
            f"border-radius: 8px; padding: 8px 18px; font-weight: 600; font-size: 13px;"
        )
        QTimer.singleShot(1500, lambda: (
            self._copy_btn.setText(orig),
            self._copy_btn.setStyleSheet(""),
        ))

    # ------------------------------------------------------------------
    # History window
    # ------------------------------------------------------------------
    def _show_history(self):
        entries = self.backend.read_history_entries()
        win = QMainWindow(self)
        win.setWindowTitle("Transcription History")
        win.resize(800, 600)
        win.setStyleSheet(global_stylesheet(_current_theme))

        central = QWidget()
        win.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Transcription History")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search history...")
        search_input.setFixedWidth(200)
        header.addWidget(search_input)

        sort_btn = QPushButton("Newest First")
        sort_btn.setObjectName("secondary")
        sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(sort_btn)

        delete_sel_btn = QPushButton("Delete Selected")
        delete_sel_btn.setStyleSheet(
            f"QPushButton {{ background-color: {_t('RED')}; color: white; border-radius: 8px; "
            f"padding: 8px 18px; font-weight: 600; font-size: 13px; }}"
            f"QPushButton:hover {{ background-color: #b91c1c; }}"
            f"QPushButton:disabled {{ background-color: #3b3b4f; color: #6b6b80; }}"
        )
        delete_sel_btn.setEnabled(False)
        header.addWidget(delete_sel_btn)

        # CHG029: export button
        export_btn = QPushButton("Export")
        export_btn.setObjectName("secondary")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(export_btn)

        clear_btn = QPushButton("Clear History")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background-color: {_t('RED')}; color: white; border-radius: 8px; "
            f"padding: 8px 18px; font-weight: 600; font-size: 13px; }}"
            f"QPushButton:hover {{ background-color: #b91c1c; }}"
        )
        header.addWidget(clear_btn)
        lay.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(scroll)

        cards_container = QWidget()
        cards_layout = QVBoxLayout(cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(10)
        scroll.setWidget(cards_container)

        state = {"newest_first": True, "query": "", "selected": set()}
        t = THEMES.get(_current_theme, THEMES["dark"])

        def _highlight(text, query):
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if not query:
                return escaped
            pat = re.escape(query.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            return re.sub(
                f"({pat})",
                f'<span style="background-color: {t["ACCENT"]}; color: white; border-radius: 3px; padding: 0 2px;">\\1</span>',
                escaped, flags=re.IGNORECASE,
            )

        def _update_del():
            n = len(state["selected"])
            delete_sel_btn.setText(f"Delete Selected ({n})" if n else "Delete Selected")
            delete_sel_btn.setEnabled(n > 0)

        def _make_card(ts, txt, query=""):
            key = (ts, txt)
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(18, 14, 18, 14)
            cl.setSpacing(6)
            tr = QHBoxLayout()
            cb = QCheckBox()
            cb.setChecked(key in state["selected"])
            tr.addWidget(cb)
            tl = QLabel(ts)
            tl.setFont(QFont("Segoe UI", 10))
            tl.setStyleSheet(f"color: {t['TEXT_DIM']};")
            tr.addWidget(tl)
            tr.addStretch()
            cl.addLayout(tr)
            lb = QLabel()
            lb.setFont(QFont("Segoe UI", 13))
            lb.setWordWrap(True)
            lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lb.setTextFormat(Qt.TextFormat.RichText)
            lb.setText(_highlight(txt, query))
            cl.addWidget(lb)

            def _on_toggle(checked):
                if checked:
                    state["selected"].add(key)
                else:
                    state["selected"].discard(key)
                card.setStyleSheet(f"QFrame#card {{ border: 2px solid {t['ACCENT']}; }}" if key in state["selected"] else "")
                _update_del()
            cb.toggled.connect(_on_toggle)
            if key in state["selected"]:
                card.setStyleSheet(f"QFrame#card {{ border: 2px solid {t['ACCENT']}; }}")
            return card

        def _populate(el):
            while cards_layout.count():
                item = cards_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            q = state["query"].strip().lower()
            filtered = [(ts, txt) for ts, txt in el if q in txt.lower() or q in ts.lower()] if q else list(el)
            if not filtered:
                lbl = QLabel("No matching results." if q else "No transcription history yet.")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cards_layout.addWidget(lbl)
                cards_layout.addStretch()
                return
            ordered = list(reversed(filtered)) if state["newest_first"] else list(filtered)
            for ts, txt in ordered:
                cards_layout.addWidget(_make_card(ts, txt, state["query"].strip()))
            cards_layout.addStretch()

        def _on_search(txt):
            state["query"] = txt
            _populate(entries)

        def _on_sort():
            state["newest_first"] = not state["newest_first"]
            sort_btn.setText("Newest First" if state["newest_first"] else "Oldest First")
            _populate(entries)

        search_input.textChanged.connect(_on_search)
        sort_btn.clicked.connect(_on_sort)

        def _do_delete():
            n = len(state["selected"])
            if n == 0:
                return
            reply = QMessageBox.question(win, "Delete", f"Delete {n} selected?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                ts_set = {ts for ts, _ in state["selected"]}
                self.backend.delete_history_entries(ts_set)
                for item in list(state["selected"]):
                    if item in entries:
                        entries.remove(item)
                state["selected"].clear()
                _update_del()
                _populate(entries)

        def _do_clear():
            reply = QMessageBox.question(win, "Clear", "Clear all history?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.backend.clear_history()
                entries.clear()
                state["selected"].clear()
                _update_del()
                _populate(entries)

        def _do_export():
            path, _ = QFileDialog.getSaveFileName(win, "Export History", "history.txt",
                                                   "Text Files (*.txt);;CSV Files (*.csv)")
            if path:
                fmt = "csv" if path.endswith(".csv") else "txt"
                self.backend.export_history(path, fmt)
                QMessageBox.information(win, "Exported", f"History exported to:\n{path}")

        delete_sel_btn.clicked.connect(_do_delete)
        clear_btn.clicked.connect(_do_clear)
        export_btn.clicked.connect(_do_export)

        _populate(entries)
        win.show()

    # ------------------------------------------------------------------
    # Theme palette
    # ------------------------------------------------------------------
    def _apply_theme_palette(self):
        t = THEMES.get(_current_theme, THEMES["dark"])
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(t["BG"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(t["TEXT_PRIMARY"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(t["BG_INPUT"]))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(t["BG_CARD"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(t["TEXT_PRIMARY"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(t["BG_CARD"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(t["TEXT_PRIMARY"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(t["ACCENT"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
        QApplication.instance().setPalette(palette)

    # ------------------------------------------------------------------
    # Close / minimize
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        if self.backend.settings.get("minimize_to_tray", True) and self._tray:
            event.ignore()
            self.hide()
        else:
            self._indicator.hide_indicator()
            self._save_settings()
            self.backend.cleanup()
            event.accept()


# =========================================================================
# Single-instance lock (prevents multiple copies from running)
# =========================================================================
_mutex_handle = None


def _acquire_single_instance():
    """Try to acquire a Windows named mutex. Returns True if this is the only instance."""
    global _mutex_handle
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, "NeuraType_SingleInstance_Mutex")
        ERROR_ALREADY_EXISTS = 183
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            # Another instance is already running
            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
            _mutex_handle = None
            return False
        return True
    except Exception:
        return True  # If mutex fails, allow launch anyway


# =========================================================================
# Entry point
# =========================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Single-instance check
    if not _acquire_single_instance():
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(
            None, "NeuraType",
            "NeuraType is already running.\n\n"
            "Check your system tray for the existing instance.",
        )
        sys.exit(0)

    settings = load_settings()
    theme = settings.get("theme", "dark")
    global _current_theme
    _current_theme = theme
    app.setStyleSheet(global_stylesheet(theme))

    t = THEMES.get(theme, THEMES["dark"])
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(t["BG"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(t["TEXT_PRIMARY"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(t["BG_INPUT"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(t["BG_CARD"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(t["TEXT_PRIMARY"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(t["BG_CARD"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(t["TEXT_PRIMARY"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(t["ACCENT"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    app.setPalette(palette)

    # --- First boot: model selection dialog ---
    if is_first_boot():
        dialog = FirstBootDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            whisper_sel, llm_sel = dialog.get_selections()
            settings["selected_whisper_models"] = whisper_sel
            settings["selected_llm_models"] = llm_sel
            # Set active whisper model to first selected
            if whisper_sel:
                settings["model"] = whisper_sel[0]
            # If user selected an LLM, enable local LLM
            if llm_sel:
                settings["use_local_llm"] = True
                settings["local_llm_model"] = llm_sel[0]
            save_settings(settings)
            mark_first_boot_done()
        else:
            # User closed without saving — use defaults
            settings["selected_whisper_models"] = ["turbo"]
            settings["selected_llm_models"] = []
            save_settings(settings)
            mark_first_boot_done()

    window = NeuraTypeWindow()

    # Force window to foreground on Windows
    try:
        import ctypes
        user32 = ctypes.windll.user32
        fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        if fg_thread != cur_thread:
            user32.AttachThreadInput(fg_thread, cur_thread, True)
        window.show()
        hwnd = int(window.winId())
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        if fg_thread != cur_thread:
            user32.AttachThreadInput(fg_thread, cur_thread, False)
    except Exception:
        window.show()
        window.raise_()
        window.activateWindow()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
