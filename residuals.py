from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QToolTip
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor

try:
    from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QLogValueAxis
    QTCHARTS_AVAILABLE = True
except ImportError:
    QTCHARTS_AVAILABLE = False

class InteractiveChartView(QChartView):
    """Visualizador do gráfico customizado para suportar zoom por scroll e reset no clique direito."""
    
    def __init__(self, chart, parent=None):
        super().__init__(chart, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRubberBand(QChartView.RectangleRubberBand)
        
    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.chart().zoom(factor)
        event.accept()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.chart().zoomReset()
            event.accept()
        else:
            super().mousePressEvent(event)

class ResidualsWidget(QWidget):
    """Painel interativo e moderno para exibir resíduos usando PySide6.QtCharts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not QTCHARTS_AVAILABLE:
            self.placeholder = QLabel("Módulo PySide6.QtCharts não disponível no ambiente.")
            layout.addWidget(self.placeholder)
            return

        # Painel de controles superiores
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

        # Configuração do Gráfico QtCharts
        self.chart = QChart()
        self.chart.setAnimationOptions(QChart.NoAnimation) # Desativa animações para performance em tempo real
        self.chart.setBackgroundRoundness(0)
        self.chart.layout().setContentsMargins(4, 4, 4, 4)
        
        # Design moderno (paleta de cinzas e legibilidade premium)
        self.chart.setBackgroundBrush(QColor("#f4f4f4"))
        self.chart.setTitleBrush(QColor("#161616"))
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        self.chart.legend().setBackgroundVisible(True)
        self.chart.legend().setBrush(QColor("#f4f4f4"))
        self.chart.legend().setPen(QColor("#c6c6c6"))
        
        self.chart_view = InteractiveChartView(self.chart, self)
        layout.addWidget(self.chart_view)

        self.history = {}
        self.time_history = {}
        self.series_dict = {}
        self.max_points = 200
        
        # Paleta de cores moderna para curvas
        self._colors = [
            "#0f62fe", "#da1e28", "#198038", "#b37600", "#8a3ffc",
            "#007d79", "#ff7eb6", "#6f3e00", "#393939", "#8c9197"
        ]

        self.axis_x = None
        self.axis_y = None
        self._setup_axes()

    def _on_settings_changed(self):
        """Reconfigura eixos e atualiza as curvas quando a escala ou tipo de eixo X são alterados."""
        self._setup_axes()
        self._refresh()

    def update_residuals(self, res_dict: dict, sim_time=None):
        """Recebe novos resíduos e insere no gráfico dinamicamente."""
        if not QTCHARTS_AVAILABLE:
            return
        for name, val in res_dict.items():
            if name not in self.history:
                self.history[name] = []
                self.time_history[name] = []
            
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
        
        self._refresh()

    def clear_history(self):
        if not QTCHARTS_AVAILABLE:
            return
        self.history = {}
        self.time_history = {}
        self.chart.removeAllSeries()
        self.series_dict = {}
        self._setup_axes()

    def _setup_axes(self):
        if not QTCHARTS_AVAILABLE:
            return
        
        # Remove eixos antigos
        if self.axis_x:
            self.chart.removeAxis(self.axis_x)
        if self.axis_y:
            self.chart.removeAxis(self.axis_y)
            
        mode = self.scale_selector.currentData()
        x_mode = self.xaxis_selector.currentData()
        
        # Eixo X
        self.axis_x = QValueAxis()
        x_label = 'Tempo de Simulação (s)' if x_mode == "time" else 'Iterações'
        self.axis_x.setTitleText(x_label)
        self.axis_x.setLabelsColor(QColor("#525252"))
        self.axis_x.setGridLinePen(QPen(QColor("#dde1e6"), 0.6))
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        
        # Eixo Y (Linear ou Logarítmico)
        if mode == "loglog":
            self.axis_y = QLogValueAxis()
            self.axis_y.setBase(10.0)
            self.axis_y.setLabelFormat("%.0e")
        else:
            self.axis_y = QValueAxis()
            self.axis_y.setLabelFormat("%.4f")
            
        self.axis_y.setTitleText('Residual')
        self.axis_y.setLabelsColor(QColor("#525252"))
        self.axis_y.setGridLinePen(QPen(QColor("#dde1e6"), 0.6))
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        
        # Reassocia eixos às curvas ativas
        for series in self.series_dict.values():
            series.attachAxis(self.axis_x)
            series.attachAxis(self.axis_y)

    def _refresh(self):
        if not QTCHARTS_AVAILABLE:
            return
            
        mode = self.scale_selector.currentData()
        x_mode = self.xaxis_selector.currentData()
        
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')
        plotted = 0
        
        for name, hist in self.history.items():
            if len(hist) < 2:
                continue
                
            if x_mode == "time" and name in self.time_history and len(self.time_history[name]) == len(hist):
                x_vals = self.time_history[name]
            else:
                x_vals = list(range(len(hist)))
                
            # Cria a série gráfica caso seja uma nova variável
            if name not in self.series_dict:
                series = QLineSeries()
                series.setName(name)
                
                pen = QPen()
                pen.setWidthF(1.8)
                color_hex = self._colors[len(self.series_dict) % len(self._colors)]
                pen.setColor(QColor(color_hex))
                series.setPen(pen)
                
                # Exibição de Tooltip interativo ao passar o mouse
                series.hovered.connect(lambda point, state, s_name=name: self._on_point_hovered(point, state, s_name))
                
                self.chart.addSeries(series)
                series.attachAxis(self.axis_x)
                series.attachAxis(self.axis_y)
                self.series_dict[name] = series
                self._update_legend_connections()
                
            series = self.series_dict[name]
            points = []
            
            for x, y in zip(x_vals, hist):
                if mode == "loglog" and y <= 0:
                    y = 1e-12 # Valor mínimo seguro para escala log
                points.append(QPointF(x, y))
                
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y
                
            series.replace(points)
            plotted += 1
            
        # Atualiza os limites de exibição dinamicamente
        if plotted:
            if min_x != float('inf') and max_x != float('-inf'):
                dx = max(1e-5, (max_x - min_x) * 0.02)
                self.axis_x.setRange(min_x, max_x + dx)
                
            if min_y != float('inf') and max_y != float('-inf'):
                if mode == "loglog":
                    log_min = max(1e-12, min_y)
                    self.axis_y.setRange(log_min * 0.5, max_y * 2.0)
                else:
                    dy = max(1e-5, (max_y - min_y) * 0.05)
                    self.axis_y.setRange(min_y - dy, max_y + dy)

    def _update_legend_connections(self):
        """Conecta cliques na legenda para ocultar/mostrar curvas."""
        for marker in self.chart.legend().markers():
            try:
                marker.clicked.disconnect()
            except Exception:
                pass
            marker.clicked.connect(self._on_marker_clicked)

    def _on_marker_clicked(self):
        marker = self.sender()
        if not marker:
            return
        series = marker.series()
        if not series:
            return
            
        # Inverte visibilidade da curva
        visible = not series.isVisible()
        series.setVisible(visible)
        marker.setVisible(True)
        
        # Opacidade do marcador reflete a visibilidade
        alpha = 1.0 if visible else 0.35
        brush = marker.labelBrush()
        color = brush.color()
        color.setAlphaF(alpha)
        brush.setColor(color)
        marker.setLabelBrush(brush)

    def _on_point_hovered(self, point, state, series_name):
        """Mostra tooltip moderno com coordenadas do ponto sob o mouse."""
        if state:
            x_mode = self.xaxis_selector.currentData()
            x_unit = "s" if x_mode == "time" else "it"
            QToolTip.showText(
                self.cursor().pos(),
                f"{series_name}\nX: {point.x():.4f} {x_unit}\nY: {point.y():.2e}",
                self
            )
        else:
            QToolTip.hideText()
