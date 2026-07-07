from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QComboBox, QPushButton
from PySide6.QtCore import QTimer

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False


class ResidualsWidget(QWidget):
    """Painel para exibir resíduos do solver em tempo real.

    Permite plotar em função de iterações ou do tempo da simulação com alta performance.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not MATPLOTLIB_AVAILABLE:
            self.placeholder = QLabel("Matplotlib não disponível — instale o matplotlib para ver os gráficos de resíduos.")
            layout.addWidget(self.placeholder)
            self._data = {}
            return

        controls = QHBoxLayout()
        self.scale_selector = QComboBox()
        self.scale_selector.addItem("Escala: Linear", "linear")
        self.scale_selector.addItem("Escala: Logarítmica", "loglog")
        self.scale_selector.currentIndexChanged.connect(self._on_settings_changed)

        self.xaxis_selector = QComboBox()
        self.xaxis_selector.addItem("Eixo X: Tempo", "time")
        self.xaxis_selector.addItem("Eixo X: Iterações", "iterations")
        self.xaxis_selector.currentIndexChanged.connect(self._on_settings_changed)

        self.clear_btn = QPushButton("Limpar")
        self.clear_btn.clicked.connect(self.clear_history)

        controls.addWidget(self.scale_selector)
        controls.addWidget(self.xaxis_selector)
        controls.addStretch(1)
        controls.addWidget(self.clear_btn)
        layout.addLayout(controls)

        self.figure = Figure(figsize=(4, 3))
        self.canvas = FigureCanvas(self.figure)
        self.figure.patch.set_facecolor("#f4f4f4")
        layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)
        self.lines = {}
        self.history = {}
        self.time_history = {}
        self.series_visible = {}
        self.max_points = 200
        self._colors = [
            "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
            "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"
        ]
        self._legend_pick_map = {}
        self.canvas.mpl_connect('pick_event', self._on_pick)

        self._setup_axes()

    def _on_settings_changed(self):
        """Recria o gráfico a partir do zero quando as configurações de eixos/escala mudam."""
        self._setup_axes()
        self._refresh()

    def update_residuals(self, res_dict: dict, sim_time=None):
        """Adiciona novos resíduos e atualiza o gráfico de forma incremental e otimizada."""
        if not MATPLOTLIB_AVAILABLE:
            return
        for name, val in res_dict.items():
            if name not in self.history:
                self.history[name] = []
                self.time_history[name] = []
            if name not in self.series_visible:
                self.series_visible[name] = True
            
            self.history[name].append(float(val))
            
            # Garante escala monotônica no eixo do tempo
            if sim_time is not None:
                t_val = sim_time
            elif self.time_history[name]:
                t_val = self.time_history[name][-1]
            else:
                t_val = 0.0
            self.time_history[name].append(float(t_val))
            
            if len(self.history[name]) > self.max_points:
                self.history[name] = self.history[name][-self.max_points:]
                self.time_history[name] = self.time_history[name][-self.max_points:]
        
        # Dispara redesenho apenas ao receber novos dados
        self._refresh()

    def clear_history(self):
        if not MATPLOTLIB_AVAILABLE:
            return
        self.history = {}
        self.time_history = {}
        self.lines = {}
        self.series_visible = {}
        self._legend_pick_map = {}
        self._setup_axes()
        self.canvas.draw()

    def _setup_axes(self):
        if not MATPLOTLIB_AVAILABLE:
            return
        mode = self.scale_selector.currentData()
        x_mode = self.xaxis_selector.currentData()
        
        self.ax.clear()
        self.lines = {} # Limpa cache de linhas antigas do Matplotlib
        self._legend_pick_map = {}
        
        self.figure.patch.set_facecolor("#f4f4f4")
        self.ax.set_facecolor("#ffffff")
        
        x_label = 'Tempo de Simulação (s)' if x_mode == "time" else 'Iterações'
        self.ax.set_xlabel(x_label)
        self.ax.set_ylabel('Residual')
        self.ax.tick_params(colors="#525252")
        self.ax.xaxis.label.set_color("#161616")
        self.ax.yaxis.label.set_color("#161616")
        for spine in self.ax.spines.values():
            spine.set_color("#c6c6c6")
        self.ax.grid(True, which='major', linestyle='-', linewidth=0.6, alpha=0.6, color="#dde1e6")
        self.ax.grid(True, which='minor', linestyle=':', linewidth=0.4, alpha=0.45, color="#e5e5e5")
        
        if mode == "loglog":
            self.ax.set_xscale('log' if x_mode == "time" else 'linear')
            self.ax.set_yscale('log')
        else:
            self.ax.set_xscale('linear')
            self.ax.set_yscale('linear')

    def _refresh(self):
        if not MATPLOTLIB_AVAILABLE:
            return
        mode = self.scale_selector.currentData()
        x_mode = self.xaxis_selector.currentData()
        plotted = 0
        plotted_names = []
        
        for idx, (name, hist) in enumerate(self.history.items()):
            if len(hist) < 2:
                continue
            
            if x_mode == "time" and name in self.time_history and len(self.time_history[name]) == len(hist):
                x = self.time_history[name]
            else:
                if mode == "loglog":
                    x = list(range(1, len(hist) + 1))
                else:
                    x = list(range(len(hist)))
            
            # Otimização crucial: altera dados in-place se a linha já existir
            if name in self.lines:
                line = self.lines[name]
                line.set_data(x, hist)
                line.set_visible(self.series_visible.get(name, True))
            else:
                color = self._colors[len(self.lines) % len(self._colors)]
                line, = self.ax.plot(x, hist, label=name, linewidth=1.8, color=color)
                line.set_visible(self.series_visible.get(name, True))
                self.lines[name] = line
                
            plotted_names.append(name)
            plotted += 1
            
        if plotted:
            self.ax.relim()
            self.ax.autoscale_view()
            
            legend = self.ax.legend(loc='best', frameon=True, framealpha=0.85, fontsize=8)
            legend.get_frame().set_facecolor("#f4f4f4")
            legend.get_frame().set_edgecolor("#c6c6c6")
            legend_lines = legend.get_lines()
            legend_texts = legend.get_texts()
            self._legend_pick_map = {}
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
                    leg_text.set_color("#161616")
                    self._legend_pick_map[leg_text] = name
                    
        self.canvas.draw()

    def _on_pick(self, event):
        artist = getattr(event, 'artist', None)
        if artist not in self._legend_pick_map:
            return
        name = self._legend_pick_map[artist]
        self.series_visible[name] = not self.series_visible.get(name, True)
        self._refresh()
