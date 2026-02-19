from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QComboBox, QPushButton
from PySide6.QtCore import QTimer

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False


class ResidualsWidget(QWidget):
    """Panel to display solver residuals in real-time.

    Provides `update_residuals(res_dict)` where `res_dict` is a mapping
    variable_name -> float (residual value). This widget keeps a short
    history per variable and updates the plot.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not MATPLOTLIB_AVAILABLE:
            self.placeholder = QLabel("Matplotlib not available — install matplotlib to see residual plots.")
            layout.addWidget(self.placeholder)
            # keep a minimal API
            self._data = {}
            return

        controls = QHBoxLayout()
        self.scale_selector = QComboBox()
        self.scale_selector.addItem("Normal (linear-linear)", "linear")
        self.scale_selector.addItem("Log-Log", "loglog")
        self.scale_selector.currentIndexChanged.connect(self._refresh)

        self.clear_btn = QPushButton("Limpar")
        self.clear_btn.clicked.connect(self.clear_history)

        controls.addWidget(QLabel("Escala:"))
        controls.addWidget(self.scale_selector)
        controls.addStretch(1)
        controls.addWidget(self.clear_btn)
        layout.addLayout(controls)

        self.figure = Figure(figsize=(4, 3))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel('Iterações')
        self.ax.set_ylabel('Residual')
        self.lines = {}
        self.history = {}
        self.series_visible = {}
        self.max_points = 200
        self._colors = [
            "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
            "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"
        ]
        self._legend_pick_map = {}
        self.canvas.mpl_connect('pick_event', self._on_pick)

        self._setup_axes()

        # optional timer to refresh the canvas periodically
        self._timer = QTimer(self)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def update_residuals(self, res_dict: dict):
        """Append a new residual snapshot. `res_dict` maps name->value."""
        if not MATPLOTLIB_AVAILABLE:
            return
        for name, val in res_dict.items():
            if name not in self.history:
                self.history[name] = []
            if name not in self.series_visible:
                self.series_visible[name] = True
            self.history[name].append(float(val))
            # limit history
            if len(self.history[name]) > self.max_points:
                self.history[name] = self.history[name][-self.max_points:]

    def clear_history(self):
        if not MATPLOTLIB_AVAILABLE:
            return
        self.history = {}
        self.lines = {}
        self.series_visible = {}
        self._legend_pick_map = {}
        self._refresh()

    def _setup_axes(self):
        if not MATPLOTLIB_AVAILABLE:
            return
        mode = self.scale_selector.currentData()
        self.ax.clear()
        self.ax.set_facecolor("#fafafa")
        self.ax.set_xlabel('Iterações')
        self.ax.set_ylabel('Residual')
        self.ax.grid(True, which='major', linestyle='-', linewidth=0.6, alpha=0.35)
        self.ax.grid(True, which='minor', linestyle=':', linewidth=0.4, alpha=0.25)
        if mode == "loglog":
            self.ax.set_xscale('log')
            self.ax.set_yscale('log')
        else:
            self.ax.set_xscale('linear')
            self.ax.set_yscale('linear')

    def _refresh(self):
        if not MATPLOTLIB_AVAILABLE:
            return
        self._setup_axes()
        mode = self.scale_selector.currentData()
        plotted = 0
        plotted_names = []
        plotted_lines = []
        self._legend_pick_map = {}
        for idx, (name, hist) in enumerate(self.history.items()):
            if len(hist) < 2:
                continue
            if mode == "loglog":
                x = list(range(1, len(hist) + 1))
            else:
                x = list(range(len(hist)))
            color = self._colors[idx % len(self._colors)]
            line, = self.ax.plot(x, hist, label=name, linewidth=1.8, color=color)
            line.set_visible(self.series_visible.get(name, True))
            self.lines[name] = line
            plotted_names.append(name)
            plotted_lines.append(line)
            plotted += 1
        if plotted:
            legend = self.ax.legend(loc='best', frameon=True, framealpha=0.85, fontsize=8)
            legend_lines = legend.get_lines()
            legend_texts = legend.get_texts()
            for i, name in enumerate(plotted_names):
                visible = self.series_visible.get(name, True)
                if i < len(legend_lines):
                    leg_line = legend_lines[i]
                    leg_line.set_picker(8)
                    leg_line.set_alpha(1.0 if visible else 0.25)
                    self._legend_pick_map[leg_line] = name
                if i < len(legend_texts):
                    leg_text = legend_texts[i]
                    leg_text.set_picker(True)
                    leg_text.set_alpha(1.0 if visible else 0.45)
                    self._legend_pick_map[leg_text] = name
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _on_pick(self, event):
        artist = getattr(event, 'artist', None)
        if artist not in self._legend_pick_map:
            return
        name = self._legend_pick_map[artist]
        self.series_visible[name] = not self.series_visible.get(name, True)
        self._refresh()
