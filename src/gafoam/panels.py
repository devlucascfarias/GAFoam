"""Painéis auxiliares da janela principal."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gafoam import foamdict

DEFAULT_RESIDUAL_TARGET = 1e-5


class ConvergenceMonitorWidget(QWidget):
    """Monitor de convergência em tempo real acoplado à aba de simulação."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("Status de Convergência", self)
        title.setStyleSheet("font-weight: bold; color: #495057; font-size: 10pt;")
        layout.addWidget(title)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Variável", "Atual", "Meta"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget { gridline-color: #dee2e6; border: 1px solid #ced4da; border-radius: 4px; font-size: 8.5pt; }"
            "QHeaderView::section { background-color: #f1f3f5; border: 1px solid #dee2e6; font-weight: bold; padding: 2px; }"
        )
        layout.addWidget(self.table)
        self.targets = {}

    def load_case(self, case_path):
        """Carrega os limites de convergência declarados no fvSolution."""
        self.targets = foamdict.parse_residual_controls(case_path) if case_path else {}
        self.table.setRowCount(0)

    def update_residual(self, name, val):
        """Atualiza a tabela com o resíduo mais recente de cada variável."""
        row = self._row_for(name)

        item_val = QTableWidgetItem(f"{val:.2e}")
        try:
            target = float(self.table.item(row, 2).text())
        except (AttributeError, ValueError):
            target = DEFAULT_RESIDUAL_TARGET

        if val <= target:
            item_val.setForeground(QColor("#137333"))
            item_val.setToolTip("Convergido!")
        else:
            item_val.setForeground(QColor("#d9381e"))

        self.table.setItem(row, 1, item_val)

    def _row_for(self, name):
        """Índice da linha da variável, criando-a com sua meta se ainda não existir."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.text() == name:
                return row

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        target = foamdict.match_residual_target(
            self.targets, name, DEFAULT_RESIDUAL_TARGET
        )
        self.table.setItem(row, 2, QTableWidgetItem(f"{target:.1e}"))
        return row


class ControlDictDockWidget(QDockWidget):
    """Painel lateral dockable para inspecionar e alterar parâmetros do controlDict."""

    def __init__(self, parent=None):
        super().__init__("Parâmetros do Caso (controlDict)", parent)
        self.main_window = parent
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        container = QWidget()
        container.setStyleSheet("background-color: #f8f9fa; border-top: 1px solid #dee2e6;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        form = QFormLayout()
        self.txt_app = QLabel("-")
        self.txt_app.setStyleSheet("font-weight: bold; color: #495057;")
        form.addRow("Solver:", self.txt_app)

        self.spin_endtime = QDoubleSpinBox()
        self.spin_endtime.setRange(0, 1e9)
        self.spin_endtime.setDecimals(4)
        form.addRow("Tempo Final:", self.spin_endtime)

        self.spin_deltat = QDoubleSpinBox()
        self.spin_deltat.setRange(1e-12, 1e9)
        self.spin_deltat.setDecimals(8)
        form.addRow("Passo deltaT:", self.spin_deltat)

        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setRange(0, 1e9)
        self.spin_interval.setDecimals(4)
        form.addRow("Gravação:", self.spin_interval)

        layout.addLayout(form)

        self.btn_save = QPushButton("Salvar Alterações")
        self.btn_save.setStyleSheet(
            "background-color: #1a73e8; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
        )
        self.btn_save.clicked.connect(self.save_parameters)
        layout.addWidget(self.btn_save)

        layout.addStretch(1)
        self.setWidget(container)

        self.current_case_path = None
        self.setEnabled(False)

    def load_case(self, case_path):
        """Popula os campos com os parâmetros do caso, desabilitando o painel se não houver."""
        self.current_case_path = case_path
        if not case_path:
            self.setEnabled(False)
            return

        params = foamdict.read_control_dict(case_path)
        if not params:
            self.setEnabled(False)
            return

        self.setEnabled(True)
        self.txt_app.setText(params.get("application", "-"))
        self._set_spin(self.spin_endtime, params.get("endTime"), 0.0)
        self._set_spin(self.spin_deltat, params.get("deltaT"), 0.001)
        self._set_spin(self.spin_interval, params.get("writeInterval"), 100.0)

    @staticmethod
    def _set_spin(spin, raw_value, fallback):
        try:
            spin.setValue(float(raw_value))
        except (TypeError, ValueError):
            spin.setValue(fallback)

    def save_parameters(self):
        if not self.current_case_path:
            return

        values = {
            "endTime": str(self.spin_endtime.value()),
            "deltaT": str(self.spin_deltat.value()),
            "writeInterval": str(self.spin_interval.value()),
        }

        if not foamdict.write_control_dict(self.current_case_path, values):
            QMessageBox.critical(self, "Erro", "Falha ao atualizar controlDict.")
            return

        QMessageBox.information(self, "Sucesso", "Parâmetros salvos com sucesso!")
        if hasattr(self.main_window, "log"):
            self.main_window.log("Parâmetros do controlDict atualizados.\n")
        self._reload_open_editor()

    def _reload_open_editor(self):
        """Recarrega o controlDict no editor caso ele esteja aberto em uma aba."""
        dict_path = foamdict.control_dict_path(self.current_case_path)
        editors = getattr(self.main_window, "path_to_editor", None)
        if not editors:
            return
        editor = editors.get(dict_path)
        if editor is None:
            return
        try:
            with open(dict_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return
        editor.blockSignals(True)
        editor.setPlainText(content)
        editor.blockSignals(False)
