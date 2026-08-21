from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QToolTip
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont

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

        self.scale_mode = "loglog"
        self.xaxis_mode = "time"
        self.filter_mode = "all"

        # Configuração do Gráfico QtCharts
        self.chart = QChart()
        self.chart.setAnimationOptions(QChart.NoAnimation) # Desativa animações para performance em tempo real
        self.chart.setBackgroundRoundness(0)
        self.chart.layout().setContentsMargins(4, 4, 4, 4)
        
        # Design moderno (paleta de cinzas e legibilidade premium)
        self.chart.setBackgroundBrush(QColor("#f4f4f4"))
        self.chart.setTitleBrush(QColor("#161616"))
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignRight)
        legend_font = QFont("Inter", 8)
        self.chart.legend().setFont(legend_font)

        self.chart.legend().setBackgroundVisible(True)
        self.chart.legend().setBrush(QColor("#f4f4f4"))
        self.chart.legend().setPen(QColor("#c6c6c6"))
        
        self.chart_view = InteractiveChartView(self.chart, self)
        layout.addWidget(self.chart_view)

        self.history = {}
        self.time_history = {}
        self.series_dict = {}
        self.series_visible = {}
        self.max_points = 3000
        
        # Paleta de cores moderna para curvas
        self._colors = [
            "#0f62fe", "#da1e28", "#198038", "#b37600", "#8a3ffc",
            "#007d79", "#ff7eb6", "#6f3e00", "#393939", "#8c9197"
        ]

        self.axis_x = None
        self.axis_y = None
        self._setup_axes()

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
        self._connected_markers = set()
        self._setup_axes()

    def _setup_axes(self):
        if not QTCHARTS_AVAILABLE:
            return
        
        # Remove eixos antigos
        if self.axis_x:
            self.chart.removeAxis(self.axis_x)
        if self.axis_y:
            self.chart.removeAxis(self.axis_y)
            
        mode = getattr(self, 'scale_mode', 'loglog')
        x_mode = getattr(self, 'xaxis_mode', 'time')
        
        # Eixo X (Logarítmico para Time em logxlog)
        if mode == "loglog" and x_mode == "time":
            self.axis_x = QLogValueAxis()
            self.axis_x.setBase(10.0)
            self.axis_x.setRange(1e-5, 10.0)
            self.axis_x.setLabelFormat("%.0e")
        else:
            self.axis_x = QValueAxis()
            self.axis_x.setLabelFormat("%.4f")
            
        self.axis_x.setTitleText('Tempo de Simulação (s)' if x_mode == "time" else 'Iterações')
        self.axis_x.setLabelsColor(QColor("#525252"))
        self.axis_x.setGridLinePen(QPen(QColor("#cccccc"), 0.8)) # Grade principal visível
        self.axis_x.setMinorGridLineVisible(True)                 # Subgrade quadriculada
        self.axis_x.setMinorGridLinePen(QPen(QColor("#e5e5e5"), 0.5, Qt.DashLine))
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        
        # Eixo Y (Logarítmico)
        if mode == "loglog":
            self.axis_y = QLogValueAxis()
            self.axis_y.setBase(10.0)
            self.axis_y.setRange(1e-12, 1.0)
            self.axis_y.setLabelFormat("%.0e")
        else:
            self.axis_y = QValueAxis()
            self.axis_y.setLabelFormat("%.4f")
            
        self.axis_y.setTitleText('Residual')
        self.axis_y.setLabelsColor(QColor("#525252"))
        self.axis_y.setGridLinePen(QPen(QColor("#cccccc"), 0.8)) # Grade principal visível
        self.axis_y.setMinorGridLineVisible(True)                 # Subgrade quadriculada
        self.axis_y.setMinorGridLinePen(QPen(QColor("#e5e5e5"), 0.5, Qt.DashLine))
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        
        # Reassocia eixos às curvas ativas
        for series in self.series_dict.values():
            series.attachAxis(self.axis_x)
            series.attachAxis(self.axis_y)

    def _refresh(self):
        if not QTCHARTS_AVAILABLE:
            return
            
        mode = getattr(self, 'scale_mode', 'loglog')
        filter_mode = getattr(self, 'filter_mode', 'all')
        x_mode = getattr(self, 'xaxis_mode', 'time')
        
        min_x = float('inf')
        max_x = float('-inf')
        min_y = float('inf')
        max_y = float('-inf')
        
        plotted = 0
        
        for name, hist in self.history.items():
            if not hist:
                continue
                
            if x_mode == "time":
                x_vals = self.time_history.get(name, [])
                if len(x_vals) != len(hist):
                    x_vals = list(range(len(hist)))
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
            
            # Ignora as primeiras iterações para cálculo dos limites
            ignore_count = 3 if len(hist) > 6 else (1 if len(hist) > 3 else 0)
            calc_x = x_vals[ignore_count:]
            calc_hist = hist[ignore_count:]

            for x, y in zip(x_vals, hist):
                if mode == "loglog":
                    x = max(1e-6, float(x))
                    y = max(1e-12, float(y))
                points.append(QPointF(x, y))
                
            # Calcula limites com base nos dados filtrados
            for x, y in zip(calc_x, calc_hist):
                if mode == "loglog":
                    x = max(1e-6, float(x))
                    y = max(1e-12, float(y))
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y
                
            series.replace(points)
            
            # Aplica filtro de equação e checklist de visibilidade
            is_visible = self.series_visible.get(name, True)
            if is_visible:
                if filter_mode == "velocities" and not any(k in name.lower() for k in ("u", "ux", "uy", "uz", "|u|")):
                    is_visible = False
                elif filter_mode == "pressure" and not any(k == name.lower() for k in ("p", "p_rgh")):
                    is_visible = False
                elif filter_mode == "turbulence" and not any(k in name.lower() for k in ("k", "epsilon", "omega", "nut", "nutilda", "t")):
                    is_visible = False
            series.setVisible(is_visible)
            
            plotted += 1
            
        # Atualiza os limites de exibição dinamicamente
        if plotted:
            if min_x != float('inf') and max_x != float('-inf'):
                if mode == "loglog" and x_mode == "time":
                    log_min_x = max(1e-6, min_x if min_x > 0 else 1e-6)
                    log_max_x = max(log_min_x * 1.5, max_x if max_x > 0 else 1.0)
                    self.axis_x.setRange(log_min_x, log_max_x)
                else:
                    dx = max(1e-5, (max_x - min_x) * 0.02)
                    self.axis_x.setRange(min_x, max_x + dx)
                
            if min_y != float('inf') and max_y != float('-inf'):
                if mode == "loglog":
                    log_min = max(1e-12, min_y if min_y > 0 else 1e-6)
                    log_max = max(log_min * 10, max_y * 1.5 if max_y > 0 else 1.0)
                    self.axis_y.setRange(log_min, log_max)
                else:
                    dy = max(1e-5, (max_y - min_y) * 0.05)
                    self.axis_y.setRange(min_y - dy, max_y + dy)

    def _update_legend_connections(self):
        """Conecta cliques na legenda para ocultar/mostrar curvas."""
        if not hasattr(self, '_connected_markers'):
            self._connected_markers = set()
        for marker in self.chart.legend().markers():
            if marker not in self._connected_markers:
                marker.clicked.connect(self._on_marker_clicked)
                self._connected_markers.add(marker)

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
        self.series_visible[series.name()] = visible
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
            x_mode = getattr(self, 'xaxis_mode', 'time')
            x_unit = "s" if x_mode == "time" else "it"
            QToolTip.showText(
                self.cursor().pos(),
                f"{series_name}\nTime: {point.x():.4g} {x_unit}\nResidual: {point.y():.2e}",
                self
            )
        else:
            QToolTip.hideText()
