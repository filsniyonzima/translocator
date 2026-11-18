"""
EMSO — RF Signal Detection Interface (v3, dashboard layout)
- Left sidebar: signal cards (click one to analyze it)
- Center panel: blank by default content area that shows whichever view is
  active — spectrum overview, bearing detail, or the map — swapped via a
  QStackedWidget so nothing pops out of the app window.
- Radio Frequency Range: full geolocation fields (bearing, distance, position)
- Wireless Range: frequency/strength/security only, no geolocation
- Position for the map is auto-detected via free IP-based lookup (no API key,
  no billing). Swap for a real GPS module later — same downstream math.
"""
import sys
import os
import random
import math

# --- Fix for radioconda environments with both Qt5 and Qt6 installed ---
# Without this, PyQt5 can fail to find its "windows" platform plugin and
# crash silently. Uses CONDA_PREFIX so this works on any teammate's machine.
_conda_prefix = os.environ.get("CONDA_PREFIX", "")
if _conda_prefix:
    _qt5_plugin_root = os.path.join(_conda_prefix, "Library", "plugins")
    _qt5_plugin_path = os.path.join(_qt5_plugin_root, "platforms")
    if os.path.isdir(_qt5_plugin_path):
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _qt5_plugin_path
        os.environ["QT_PLUGIN_PATH"] = _qt5_plugin_root

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QScrollArea, QStackedWidget, QGridLayout,
    QInputDialog
)
from PyQt5.QtCore import Qt, QTimer
import pyqtgraph as pg
from wifi_scanner import scan_wifi
from geolocation import local_to_latlon
from geomap import open_in_browser, locate_via_ip, embed_url

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_OK = True
except ImportError:
    WEBENGINE_OK = False

NAVY = "#1F3864"
ACCENT = "#2E74B5"
BG = "#0F1620"
PANEL_BG = "#121B28"
CARD_BG = "#1A2433"
CARD_BG_SEL = "#223049"
TEXT = "#E8ECF2"
SUBTEXT = "#8FA2BD"
GOOD = "#3FB27F"
WARN = "#D9731C"

STYLE = f"""
QMainWindow {{ background-color: {BG}; }}
QWidget {{ background-color: {BG}; color: {TEXT}; font-family: 'Segoe UI'; }}
QWidget#sidebar {{ background-color: {PANEL_BG}; border-radius: 12px; }}
QWidget#centerPanel {{ background-color: {PANEL_BG}; border-radius: 12px; }}
QPushButton#tabBtn {{
    background-color: {CARD_BG}; color: {SUBTEXT}; border: none;
    padding: 12px 28px; font-size: 14px; font-weight: 600; border-radius: 8px;
}}
QPushButton#tabBtn:checked {{ background-color: {ACCENT}; color: white; }}
QPushButton#scanBtn {{
    background-color: {GOOD}; color: white; border: none;
    padding: 10px 24px; font-size: 13px; font-weight: 600; border-radius: 8px;
}}
QPushButton#scanBtn:checked {{ background-color: {WARN}; }}
QPushButton#backBtn {{
    background-color: {CARD_BG}; color: {TEXT}; border: 1px solid #2A3647;
    padding: 8px 18px; font-size: 12px; font-weight: 600; border-radius: 6px;
}}
QFrame#card {{
    background-color: {CARD_BG}; border-radius: 12px; border: 1px solid #2A3647;
}}
QFrame#cardSelected {{
    background-color: {CARD_BG_SEL}; border-radius: 12px; border: 1px solid {ACCENT};
}}
QLabel#cardTitle {{ color: {TEXT}; font-size: 15px; font-weight: 700; }}
QLabel#cardField {{ color: {SUBTEXT}; font-size: 11px; }}
QLabel#cardValue {{ color: {TEXT}; font-size: 12px; font-weight: 600; }}
QLabel#header {{ color: {TEXT}; font-size: 20px; font-weight: 700; }}
QLabel#subheader {{ color: {SUBTEXT}; font-size: 12px; }}
QLabel#bigStat {{ color: {ACCENT}; font-size: 19px; font-weight: 700; }}
QLabel#placeholder {{ color: {SUBTEXT}; font-size: 16px; }}
"""

MODULATIONS = ["FM", "AM", "DMR (digital)", "P25 (digital)", "FSK"]
ENCRYPTION = ["Unencrypted", "Unencrypted", "Unencrypted", "Encryption indicators present"]
WIFI_SECURITY = ["WPA2", "WPA3", "Open (unsecured)"]


def generate_radio_signal():
    is_vhf = random.random() > 0.5
    freq = round(random.uniform(136.0, 174.0) if is_vhf
                 else random.uniform(400.0, 470.0), 3)
    band = "VHF" if is_vhf else "UHF"
    modulation = random.choice(MODULATIONS)
    is_digital = modulation in ("DMR (digital)", "P25 (digital)")
    label = f"{band} • {modulation if is_digital else modulation + ' Transmission'}"
    bearing = random.uniform(0, 360)
    distance = random.randint(30, 400)
    return {
        "label": label,
        "freq": f"{freq} MHz",
        "freq_num": freq,
        "strength": random.randint(-95, -40),
        "modulation": modulation,
        "encryption": random.choice(ENCRYPTION),
        "bearing": bearing,
        "distance": distance,
        "coords": f"S {random.uniform(1.9,2.1):.4f}°, E {random.uniform(30.0,30.2):.4f}°",
    }


def generate_wifi_signal():
    freq = round(random.choice([2412, 2437, 2462, 5180, 5220]) + random.uniform(-2, 2), 1)
    band_label = "2.4 GHz Wi-Fi" if freq < 3000 else "5 GHz Wi-Fi"
    return {
        "label": band_label,
        "freq": f"{freq} MHz",
        "freq_num": freq,
        "strength": random.randint(-90, -35),
        "security": random.choice(WIFI_SECURITY),
    }


class SignalCard(QFrame):
    def __init__(self, idx, fields, clickable=False, on_click=None):
        super().__init__()
        self.idx = idx
        self.setObjectName("card")
        self.setMinimumHeight(140)
        self.setMinimumWidth(260)
        self.clickable = clickable
        self.on_click = on_click
        self.selected = False
        if clickable:
            self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        title_row = QHBoxLayout()
        self.title = QLabel(f"Signal {idx}")
        self.title.setObjectName("cardTitle")
        self.title.setWordWrap(True)
        title_row.addWidget(self.title, stretch=1)
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color:{GOOD}; font-size:12px;")
        title_row.addWidget(self.dot)
        layout.addLayout(title_row)

        if clickable:
            hint = QLabel("click to analyze →")
            hint.setObjectName("cardField")
            layout.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(3)
        self.fields = {}
        for i, name in enumerate(fields):
            lbl = QLabel(name.upper())
            lbl.setObjectName("cardField")
            val = QLabel("—")
            val.setObjectName("cardValue")
            val.setWordWrap(True)
            grid.addWidget(lbl, i, 0)
            grid.addWidget(val, i, 1)
            self.fields[name] = val
        layout.addLayout(grid)

    def mousePressEvent(self, event):
        if self.clickable and self.on_click:
            self.on_click(self.idx)
        super().mousePressEvent(event)

    def set_selected(self, sel):
        self.selected = sel
        self.setObjectName("cardSelected" if sel else "card")
        self.setStyleSheet("")
        self.style().unpolish(self)
        self.style().polish(self)

    def update_data(self, data):
        self.title.setText(data["label"])
        if "Modulation" in self.fields:
            self.fields["Frequency"].setText(data["freq"])
            self.fields["Strength"].setText(f'{data["strength"]} dBm')
            self.fields["Modulation"].setText(data["modulation"])
            enc = data["encryption"]
            color = WARN if "indicators" in enc else SUBTEXT
            self.fields["Encryption"].setText(enc)
            self.fields["Encryption"].setStyleSheet(f"color:{color}; font-size:12px; font-weight:600;")
            self.fields["Bearing"].setText(f'{data["bearing"]:.0f}°')
            self.fields["Est. Distance"].setText(f'{data["distance"]} m')
            self.fields["Est. Position"].setText(data["coords"])
        else:
            self.fields["Frequency"].setText(data["freq"])
            self.fields["Strength"].setText(f'{data["strength"]} dBm')
            self.fields["Security"].setText(data["security"])
        self._data = data


class RadioPage(QWidget):
    """Dashboard layout: cards on the left, center panel shows overview / detail / map."""
    FIELDS = ["Frequency", "Strength", "Modulation", "Encryption", "Bearing", "Est. Distance", "Est. Position"]

    def __init__(self):
        super().__init__()
        self.selected_idx = None
        self.origin_latlon = None
        self.data_cache = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # ---------------- LEFT SIDEBAR ----------------
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 16, 16, 16)
        sb_layout.setSpacing(10)

        header = QLabel("Radio Frequency Range")
        header.setObjectName("header")
        header.setWordWrap(True)
        sb_layout.addWidget(header)

        self.sub = QLabel("Click a signal to analyze it.")
        self.sub.setObjectName("subheader")
        self.sub.setWordWrap(True)
        sb_layout.addWidget(self.sub)

        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setFrameShape(QFrame.NoFrame)
        cards_container = QWidget()
        cards_layout = QVBoxLayout(cards_container)
        cards_layout.setSpacing(10)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards = [SignalCard(i + 1, self.FIELDS, clickable=True, on_click=self.select_signal)
                      for i in range(4)]
        for c in self.cards:
            cards_layout.addWidget(c)
        cards_layout.addStretch()
        cards_scroll.setWidget(cards_container)
        sb_layout.addWidget(cards_scroll, stretch=1)

        root.addWidget(sidebar)

        # ---------------- CENTER PANEL ----------------
        center = QWidget()
        center.setObjectName("centerPanel")
        center_outer = QVBoxLayout(center)
        center_outer.setContentsMargins(20, 18, 20, 18)

        self.center_stack = QStackedWidget()
        center_outer.addWidget(self.center_stack)
        root.addWidget(center, stretch=1)

        # -- page 0: overview spectrum (default/blank-ish starting view) --
        overview_page = QWidget()
        ov = QVBoxLayout(overview_page)
        ov.setContentsMargins(0, 0, 0, 0)
        ov_label = QLabel("SPECTRUM OVERVIEW — FREQUENCY (MHz) vs STRENGTH (dBm)")
        ov_label.setObjectName("cardField")
        ov.addWidget(ov_label)
        self.overview_plot = pg.PlotWidget()
        self.overview_plot.setBackground(CARD_BG)
        self.overview_plot.showGrid(x=True, y=True, alpha=0.2)
        self.overview_plot.setLabel('bottom', 'Frequency (MHz)')
        self.overview_plot.setLabel('left', 'Strength (+100 dBm)')
        ov.addWidget(self.overview_plot, stretch=1)
        placeholder = QLabel("Select a signal on the left to see its bearing and location here.")
        placeholder.setObjectName("placeholder")
        placeholder.setAlignment(Qt.AlignCenter)
        ov.addWidget(placeholder)
        self.center_stack.addWidget(overview_page)  # index 0

        # -- page 1: detail (bearing chart + stats + map button) --
        detail_page = QWidget()
        dl = QVBoxLayout(detail_page)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(12)

        d_header = QHBoxLayout()
        self.detail_title = QLabel("")
        self.detail_title.setObjectName("header")
        d_header.addWidget(self.detail_title, stretch=1)
        self.back_btn = QPushButton("← Back to overview")
        self.back_btn.setObjectName("backBtn")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.show_overview)
        d_header.addWidget(self.back_btn)
        self.map_btn = QPushButton("📍 View on Map")
        self.map_btn.setObjectName("backBtn")
        self.map_btn.setCursor(Qt.PointingHandCursor)
        self.map_btn.clicked.connect(self.show_on_map)
        d_header.addWidget(self.map_btn)
        dl.addLayout(d_header)

        self.chart_label = QLabel("BEARING SWEEP — ANGLE (°) vs STRENGTH (dBm)")
        self.chart_label.setObjectName("cardField")
        dl.addWidget(self.chart_label)

        stats_row = QHBoxLayout()
        self.bearing_stat = QLabel("")
        self.bearing_stat.setObjectName("bigStat")
        self.distance_stat = QLabel("")
        self.distance_stat.setObjectName("bigStat")
        stats_row.addWidget(self.bearing_stat)
        stats_row.addSpacing(40)
        stats_row.addWidget(self.distance_stat)
        stats_row.addStretch()
        dl.addLayout(stats_row)

        self.plot = pg.PlotWidget()
        self.plot.setBackground(CARD_BG)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setLabel('bottom', 'Antenna angle (°)')
        self.plot.setLabel('left', 'Strength (dBm)')
        dl.addWidget(self.plot, stretch=1)
        self.center_stack.addWidget(detail_page)  # index 1

        # -- page 2: map --
        map_page = QWidget()
        ml = QVBoxLayout(map_page)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(12)
        m_header = QHBoxLayout()
        map_title = QLabel("Estimated Source Location")
        map_title.setObjectName("header")
        m_header.addWidget(map_title, stretch=1)
        self.map_back_btn = QPushButton("← Back to analysis")
        self.map_back_btn.setObjectName("backBtn")
        self.map_back_btn.setCursor(Qt.PointingHandCursor)
        self.map_back_btn.clicked.connect(lambda: self.center_stack.setCurrentIndex(1))
        m_header.addWidget(self.map_back_btn)
        ml.addLayout(m_header)

        self.map_status = QLabel("")
        self.map_status.setObjectName("subheader")
        ml.addWidget(self.map_status)

        if WEBENGINE_OK:
            self.map_view = QWebEngineView()
            ml.addWidget(self.map_view, stretch=1)
        else:
            self.map_view = None
            fallback = QLabel("Embedded map unavailable here — opened in your browser instead.")
            fallback.setObjectName("placeholder")
            fallback.setAlignment(Qt.AlignCenter)
            ml.addWidget(fallback, stretch=1)
        self.center_stack.addWidget(map_page)  # index 2

        self.data_cache = [generate_radio_signal() for _ in self.cards]
        self.center_stack.setCurrentIndex(0)

    def select_signal(self, idx):
        self.selected_idx = idx
        for c in self.cards:
            c.set_selected(c.idx == idx)
        data = self.data_cache[idx - 1]
        self.detail_title.setText(data["label"])
        self.sub.setText(f"Analyzing Signal {idx}.")
        self.center_stack.setCurrentIndex(1)
        self.render_detail()

    def show_overview(self):
        self.selected_idx = None
        for c in self.cards:
            c.set_selected(False)
        self.sub.setText("Click a signal to analyze it.")
        self.center_stack.setCurrentIndex(0)
        self.render_overview()

    def refresh(self):
        self.data_cache = [generate_radio_signal() for _ in self.cards]
        for c, d in zip(self.cards, self.data_cache):
            c.update_data(d)
        if self.center_stack.currentIndex() == 0:
            self.render_overview()
        elif self.center_stack.currentIndex() == 1:
            self.render_detail()

    def show_on_map(self):
        if self.selected_idx is None:
            return
        data = self.data_cache[self.selected_idx - 1]

        if self.origin_latlon is None:
            lat_str, ok1 = QInputDialog.getText(
                self, "Your real position (one-time)",
                "You're standing next to the receiver/access point right now.\n"
                "Read your phone's GPS and enter your latitude (e.g. -2.23375):")
            if not ok1 or not lat_str.strip():
                return
            lon_str, ok2 = QInputDialog.getText(
                self, "Your real position (one-time)",
                "Now your longitude (e.g. 30.18115):")
            if not ok2 or not lon_str.strip():
                return
            try:
                self.origin_latlon = (float(lat_str), float(lon_str))
            except ValueError:
                self.map_status.setText("Invalid input — please enter plain numbers.")
                return

        origin_lat, origin_lon = self.origin_latlon
        bearing_rad = math.radians(data["bearing"])
        distance = data["distance"]
        dx = distance * math.sin(bearing_rad)
        dy = distance * math.cos(bearing_rad)
        est_lat, est_lon = local_to_latlon(origin_lat, origin_lon, dx, dy)

        self.center_stack.setCurrentIndex(2)
        self.map_status.setText(
            f"Signal {self.selected_idx} — estimated at {est_lat:.5f}, {est_lon:.5f} "
            f"(from your entered position, exact)")

        if WEBENGINE_OK:
            iframe_html = f"""
            <html><head><style>
                html, body {{ margin:0; padding:0; height:100%; background:{CARD_BG}; }}
                iframe {{ width:100%; height:100%; border:0; }}
            </style></head>
            <body><iframe src="{embed_url(est_lat, est_lon)}"></iframe></body></html>
            """
            self.map_view.setHtml(iframe_html)
        else:
            open_in_browser(est_lat, est_lon, label=f"Signal {self.selected_idx}")

    def render_overview(self):
        self.overview_plot.clear()
        freqs = [d["freq_num"] for d in self.data_cache]
        strengths = [d["strength"] + 100 for d in self.data_cache]
        bars = pg.BarGraphItem(x=freqs, height=strengths, width=3, brush=ACCENT)
        self.overview_plot.addItem(bars)

    def render_detail(self):
        if self.selected_idx is None:
            return
        data = self.data_cache[self.selected_idx - 1]
        self.bearing_stat.setText(f'Estimated bearing: {data["bearing"]:.0f}°')
        self.distance_stat.setText(f'Estimated distance: {data["distance"]} m')
        angles = list(range(0, 361, 5))
        true_bearing = data["bearing"]
        vals = []
        for a in angles:
            diff = min(abs(a - true_bearing), 360 - abs(a - true_bearing))
            peak = data["strength"] - 0.015 * diff ** 1.3 + random.uniform(-1.5, 1.5)
            vals.append(peak)
        self.plot.clear()
        self.plot.plot(angles, vals, pen=pg.mkPen(ACCENT, width=2))
        self.plot.addLine(x=true_bearing, pen=pg.mkPen(WARN, width=1, style=Qt.DashLine))


class WifiPage(QWidget):
    """Wireless Range page: cards on the left, spectrum chart in the center."""
    FIELDS = ["Frequency", "Strength", "Security"]
    EMPTY_SLOT = {"label": "No network detected", "freq": "—", "freq_num": 0,
                  "strength": -100, "security": "—"}

    def __init__(self):
        super().__init__()
        self._tick_count = 0
        self._last_scan = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 16, 16, 16)
        sb_layout.setSpacing(10)

        header = QLabel("Wireless Range")
        header.setObjectName("header")
        sb_layout.addWidget(header)
        sub = QLabel("Real Wi-Fi networks near you. No geolocation for this range.")
        sub.setObjectName("subheader")
        sub.setWordWrap(True)
        sb_layout.addWidget(sub)

        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setFrameShape(QFrame.NoFrame)
        cards_container = QWidget()
        cards_layout = QVBoxLayout(cards_container)
        cards_layout.setSpacing(10)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards = [SignalCard(i + 1, self.FIELDS) for i in range(6)]
        for c in self.cards:
            cards_layout.addWidget(c)
        cards_layout.addStretch()
        cards_scroll.setWidget(cards_container)
        sb_layout.addWidget(cards_scroll, stretch=1)
        root.addWidget(sidebar)

        center = QWidget()
        center.setObjectName("centerPanel")
        c_layout = QVBoxLayout(center)
        c_layout.setContentsMargins(20, 18, 20, 18)
        chart_label = QLabel("SPECTRUM OVERVIEW — FREQUENCY (MHz) vs STRENGTH (dBm)")
        chart_label.setObjectName("cardField")
        c_layout.addWidget(chart_label)
        self.plot = pg.PlotWidget()
        self.plot.setBackground(CARD_BG)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setLabel('bottom', 'Frequency (MHz)')
        self.plot.setLabel('left', 'Strength (+100 dBm)')
        c_layout.addWidget(self.plot, stretch=1)
        root.addWidget(center, stretch=1)

    def refresh(self):
        self._tick_count += 1
        if self._tick_count % 15 == 1 or not self._last_scan:
            self._last_scan = scan_wifi(top_n=len(self.cards))
        real = self._last_scan
        data_cache = (real + [self.EMPTY_SLOT] * len(self.cards))[:len(self.cards)]
        for c, d in zip(self.cards, data_cache):
            c.update_data(d)
        self.plot.clear()
        plot_data = [d for d in data_cache if d["freq_num"] > 0]
        if plot_data:
            freqs = [d["freq_num"] for d in plot_data]
            strengths = [d["strength"] + 100 for d in plot_data]
            bars = pg.BarGraphItem(x=freqs, height=strengths, width=3, brush=GOOD)
            self.plot.addItem(bars)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EMSO — RF Signal Detection and Geolocation")
        self.resize(1200, 780)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        top_bar = QHBoxLayout()
        self.radio_btn = QPushButton("Radio Frequency Range")
        self.wifi_btn = QPushButton("Wireless Range")
        for btn in (self.radio_btn, self.wifi_btn):
            btn.setObjectName("tabBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
        self.radio_btn.setChecked(True)
        self.radio_btn.clicked.connect(lambda: self.switch_band(0))
        self.wifi_btn.clicked.connect(lambda: self.switch_band(1))

        top_bar.addWidget(self.radio_btn)
        top_bar.addWidget(self.wifi_btn)
        top_bar.addStretch()

        self.scan_btn = QPushButton("● Scanning")
        self.scan_btn.setObjectName("scanBtn")
        self.scan_btn.setCheckable(True)
        self.scan_btn.setChecked(True)
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.clicked.connect(self.toggle_scan)
        top_bar.addWidget(self.scan_btn)

        main_layout.addLayout(top_bar)

        self.stack = QStackedWidget()
        self.radio_page = RadioPage()
        self.wifi_page = WifiPage()
        self.stack.addWidget(self.radio_page)
        self.stack.addWidget(self.wifi_page)
        main_layout.addWidget(self.stack, stretch=1)

        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def switch_band(self, index):
        self.radio_btn.setChecked(index == 0)
        self.wifi_btn.setChecked(index == 1)
        self.stack.setCurrentIndex(index)

    def toggle_scan(self):
        if self.scan_btn.isChecked():
            self.scan_btn.setText("● Scanning")
            self.timer.start(1000)
        else:
            self.scan_btn.setText("○ Paused")
            self.timer.stop()

    def tick(self):
        self.stack.currentWidget().refresh()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
