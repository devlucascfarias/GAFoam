"""Visual editor for OpenFOAM boundary conditions (0/ directory)."""

import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QLineEdit,
    QPushButton, QLabel, QMessageBox,
)
from gafoam import foamdict

COMMON_BC_TYPES = [
    "fixedValue", "zeroGradient", "noSlip", "calculated",
    "inletOutlet", "pressureInletOutletVelocity",
    "totalPressure", "symmetryPlane", "symmetry",
    "slip", "empty", "wedge", "cyclic",
    "fixedFluxPressure", "freestreamPressure",
    "turbulentIntensityKineticEnergyInlet",
    "turbulentMixingLengthDissipationRateInlet",
    "kqRWallFunction", "nutUSpaldingWallFunction",
    "omegaWallFunction", "epsilonWallFunction",
    "codedFixedValue",
]


class NoScrollComboBox(QComboBox):
    """QComboBox que ignora a rolagem do mouse quando fechado para evitar alterações acidentais de valor."""

    def wheelEvent(self, event):
        event.ignore()


class BoundaryConditionEditor(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_case = None
        self.current_field = None
        self._init_ui()
        self._apply_styles()

    def _init_ui(self):
        # Layouts
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(2)
        
        # Top toolbar
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(6, 4, 6, 4)
        self.toolbar_layout.setSpacing(6)
        
        self.reload_button = QPushButton("Reload")
        self.save_button = QPushButton("Save Changes")
        
        self.save_button.clicked.connect(self._save_changes)
        self.reload_button.clicked.connect(self._reload)
        
        self.toolbar_layout.addStretch()
        self.toolbar_layout.addWidget(self.reload_button)
        self.toolbar_layout.addWidget(self.save_button)
        
        self.main_layout.addLayout(self.toolbar_layout)
        
        # Main area
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Left panel
        self.field_list = QListWidget()
        self.field_list.currentItemChanged.connect(self._on_field_selected)
        
        # Right panel
        self.bc_table = QTableWidget()
        self.bc_table.setColumnCount(3)
        self.bc_table.setHorizontalHeaderLabels(["Patch", "Type", "Value"])
        self.bc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.bc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.bc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.bc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        self.splitter.addWidget(self.field_list)
        self.splitter.addWidget(self.bc_table)
        self.splitter.setSizes([180, 820])
        
        self.main_layout.addWidget(self.splitter)

    def _apply_styles(self):
        self.setStyleSheet("background-color: #f4f4f4;")
        
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #0f62fe;
                color: white;
                font-weight: 600;
                font-size: 11px;
                padding: 4px 10px;
                border: none;
                border-radius: 0;
            }
            QPushButton:hover {
                background-color: #0050e6;
            }
        """)
        
        self.reload_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #e0e0e0;
                color: #161616;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 0;
            }
            QPushButton:hover {
                background-color: #e5e5e5;
            }
        """)
        
        self.field_list.setStyleSheet("""
            QListWidget {
                border: none;
                border-right: 1px solid #e0e0e0;
                background-color: #f4f4f4;
                color: #161616;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 3px 6px;
            }
            QListWidget::item:selected {
                background-color: #e0e0e0;
                color: #161616;
            }
        """)
        
        self.bc_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #e0e0e0;
                border: none;
                font-size: 11px;
                background-color: #f4f4f4;
                color: #161616;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                color: #161616;
                font-size: 11px;
                font-weight: 600;
                border: none;
                border-bottom: 1px solid #c6c6c6;
                padding: 3px 6px;
            }
        """)

    def load_case(self, case_path: str):
        self.current_case = case_path
        self.current_field = None
        self.field_list.clear()
        self.bc_table.setRowCount(0)
        
        if not self.current_case:
            return
            
        try:
            fields = foamdict.list_field_files(self.current_case)
            for field in fields:
                self.field_list.addItem(QListWidgetItem(field))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to list field files: {e}")

    def _on_field_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current:
            self._load_field(current.text())

    def _load_field(self, field_name: str):
        if not self.current_case:
            return
            
        self.current_field = field_name
        self.bc_table.setRowCount(0)
        
        file_path = os.path.join(self.current_case, "0", field_name)
        try:
            boundaries = foamdict.read_boundary_field(file_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to read field {field_name}: {e}")
            return
            
        self.bc_table.setRowCount(len(boundaries))
        for row, (patch, data) in enumerate(boundaries.items()):
            # Column 0: Patch name
            patch_item = QTableWidgetItem(patch)
            patch_font = QFont("Segoe UI", 8)
            patch_item.setFont(patch_font)
            self.bc_table.setItem(row, 0, patch_item)
            
            # Column 1: Type (ComboBox)
            type_combo = NoScrollComboBox()
            type_combo.setStyleSheet(
                "QComboBox { background-color: #ffffff; color: #161616; font-size: 11px; "
                "border: none; border-bottom: 1px solid #8d8d8d; padding: 2px 4px; border-radius: 0; } "
                "QComboBox:focus { border-bottom: 2px solid #0f62fe; }"
            )

            bc_type = data.get("type", "")
            
            combo_types = COMMON_BC_TYPES.copy()
            if bc_type and bc_type not in combo_types:
                combo_types.insert(0, bc_type)
                
            type_combo.addItems(combo_types)
            if bc_type:
                type_combo.setCurrentText(bc_type)
            self.bc_table.setCellWidget(row, 1, type_combo)
            
            # Column 2: Value (LineEdit)
            value_edit = QLineEdit()
            value_edit.setStyleSheet(
                "QLineEdit { background-color: #ffffff; color: #161616; font-size: 11px; "
                "border: none; border-bottom: 1px solid #8d8d8d; padding: 2px 4px; border-radius: 0; } "
                "QLineEdit:focus { border-bottom: 2px solid #0f62fe; }"
            )
            bc_value = data.get("value", "")
            if bc_value:
                value_edit.setText(bc_value)
            self.bc_table.setCellWidget(row, 2, value_edit)


    def _save_changes(self):
        if not self.current_case or not self.current_field:
            QMessageBox.information(self, "Info", "No field selected to save.")
            return
            
        file_path = os.path.join(self.current_case, "0", self.current_field)
        
        boundaries = {}
        for row in range(self.bc_table.rowCount()):
            patch_item = self.bc_table.item(row, 0)
            if not patch_item:
                continue
            patch = patch_item.text()
            
            type_combo = self.bc_table.cellWidget(row, 1)
            value_edit = self.bc_table.cellWidget(row, 2)
            
            data = {}
            if type_combo:
                data["type"] = type_combo.currentText()
            if value_edit and value_edit.text():
                data["value"] = value_edit.text()
                
            boundaries[patch] = data
            
        try:
            foamdict.write_boundary_field(file_path, boundaries)
            QMessageBox.information(self, "Success", f"Successfully saved changes to {self.current_field}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save {self.current_field}: {e}")

    def _reload(self):
        if self.current_case:
            if self.current_field:
                self._load_field(self.current_field)
            else:
                self.load_case(self.current_case)
