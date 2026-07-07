import os
import re
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QPushButton, QLabel, QMessageBox)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter

# Verifica disponibilidade do QtCharts
try:
    from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
    QTCHARTS_AVAILABLE = True
except ImportError:
    QTCHARTS_AVAILABLE = False

class ResultsWidget(QWidget):
    """Aba de Pós-Processamento Rápido: plota coeficientes de forças, vazões e dados de postProcessing/*.dat."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        
        if not QTCHARTS_AVAILABLE:
            layout.addWidget(QLabel("Módulo PySide6.QtCharts não disponível no ambiente."))
            return
            
        # Barra superior de seleção de arquivos do postProcessing/
        top_layout = QHBoxLayout()
        
        top_layout.addWidget(QLabel("Arquivo:"))
        self.combo_files = QComboBox()
        self.combo_fields = QComboBox() # Eixo Y
        
        self.combo_files.currentIndexChanged.connect(self.load_data_file)
        self.combo_fields.currentIndexChanged.connect(self.update_plot)
        
        top_layout.addWidget(self.combo_files, 2)
        top_layout.addWidget(QLabel("Eixo Y:"))
        top_layout.addWidget(self.combo_fields, 1)
        
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.clicked.connect(self.scan_postprocessing)
        top_layout.addWidget(self.btn_refresh)
        
        layout.addLayout(top_layout)
        
        # Gráficos da simulação usando QtCharts
        self.chart = QChart()
        self.chart.setTheme(QChart.ChartTheme.ChartThemeLight)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.chart_view, 1)
        
        # Eixos
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Tempo (s)")
        self.axis_x.setLabelsColor(QColor("#525252"))
        
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("Valor")
        self.axis_y.setLabelsColor(QColor("#525252"))
        
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        
        self.current_case_path = None
        self.data_series = None
        self.parsed_data = []      # Matriz de dados [[row1], [row2], ...]
        self.header_columns = []   # Lista de nomes de colunas
        
        self.scan_postprocessing()

    def scan_postprocessing(self):
        """Varre recursivamente a pasta postProcessing/ procurando arquivos .dat."""
        if hasattr(self.main_window, 'current_case'):
            self.current_case_path = self.main_window.current_case
            
        self.combo_files.blockSignals(True)
        self.combo_files.clear()
        
        if not self.current_case_path:
            self.combo_files.blockSignals(False)
            return
            
        post_dir = os.path.join(self.current_case_path, "postProcessing")
        if not os.path.isdir(post_dir):
            self.combo_files.blockSignals(False)
            return
            
        # Busca recursiva por .dat
        found_files = []
        try:
            for root, _, files in os.walk(post_dir):
                for f in files:
                    if f.lower().endswith(('.dat', '.txt', '.out')):
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, post_dir)
                        # Ignora arquivos de log e pastas temporárias
                        if not any(k in rel_path.lower() for k in ('log', 'error', 'platforms')):
                            found_files.append((rel_path, full_path))
        except Exception:
            pass
            
        found_files.sort(key=lambda x: x[0].lower())
        for rel, full in found_files:
            self.combo_files.addItem(rel, full)
            
        self.combo_files.blockSignals(False)
        
        if found_files:
            self.load_data_file()

    def load_data_file(self):
        """Abre o arquivo selecionado, lê o cabeçalho e analisa as colunas."""
        file_path = self.combo_files.currentData()
        self.combo_fields.blockSignals(True)
        self.combo_fields.clear()
        
        self.parsed_data = []
        self.header_columns = []
        
        if not file_path or not os.path.isfile(file_path):
            self.combo_fields.blockSignals(False)
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception:
            self.combo_fields.blockSignals(False)
            return
            
        # Parse do cabeçalho de colunas
        # Geralmente os arquivos OpenFOAM têm comentários no topo, e a última linha de comentário descreve as colunas:
        # # Time    Cd    Cl    ...
        header_line = None
        for line in lines:
            if line.strip().startswith('#'):
                header_line = line
            else:
                # Primeiro registro numérico
                break
                
        # Caso tenha cabeçalho, decodifica colunas
        if header_line:
            # Remove o caractere de comentário inicial
            clean_hdr = header_line.lstrip('#').strip()
            # Divide colunas por espaços ou tabulações
            self.header_columns = re.split(r'\s+', clean_hdr)
        else:
            self.header_columns = []
            
        # Parse numérico dos dados
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            try:
                row_vals = [float(x) for x in re.split(r'\s+', stripped)]
                if row_vals:
                    self.parsed_data.append(row_vals)
            except ValueError:
                continue
                
        if not self.parsed_data:
            self.combo_fields.blockSignals(False)
            return
            
        # Sincroniza cabeçalho caso o arquivo não possua um
        num_cols = len(self.parsed_data[0])
        if len(self.header_columns) < num_cols:
            self.header_columns += [f"Coluna {i+1}" for i in range(len(self.header_columns), num_cols)]
            
        # Popula a combobox do eixo Y (ignora a coluna 0, que geralmente é o Eixo X: Tempo)
        for idx in range(1, num_cols):
            col_name = self.header_columns[idx]
            self.combo_fields.addItem(f"{col_name} (Col. {idx+1})", idx)
            
        self.combo_fields.blockSignals(False)
        self.update_plot()

    def update_plot(self):
        """Atualiza a curva gráfica correspondente ao campo selecionado."""
        if not self.parsed_data:
            self.chart.removeAllSeries()
            return
            
        y_idx = self.combo_fields.currentData()
        if y_idx is None:
            self.chart.removeAllSeries()
            return
            
        self.chart.removeAllSeries()
        
        # Cria a série e plota
        self.data_series = QLineSeries()
        self.data_series.setName(self.header_columns[y_idx])
        
        pen = QPen(QColor("#1a73e8"))
        pen.setWidthF(2.0)
        self.data_series.setPen(pen)
        
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')
        
        for row in self.parsed_data:
            if len(row) > y_idx:
                x = row[0] # Tempo
                y = row[y_idx] # Valor selecionado
                self.data_series.append(QPointF(x, y))
                
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y
                
        self.chart.addSeries(self.data_series)
        self.data_series.attachAxis(self.axis_x)
        self.data_series.attachAxis(self.axis_y)
        
        # Atualiza ranges
        if min_x != float('inf') and max_x != float('-inf'):
            self.axis_x.setRange(min_x, max_x)
            
        if min_y != float('inf') and max_y != float('-inf'):
            # Margem vertical de 5%
            dy = max(1e-6, (max_y - min_y) * 0.05)
            self.axis_y.setRange(min_y - dy, max_y + dy)
            self.axis_y.setTitleText(self.header_columns[y_idx])
            
        # Atualiza título do eixo X
        x_title = self.header_columns[0] if self.header_columns else "Tempo"
        self.axis_x.setTitleText(x_title)
