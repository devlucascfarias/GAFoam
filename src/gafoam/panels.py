"""Painéis auxiliares da janela principal."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QCheckBox,
    QWidget,
)


from gafoam import foamdict

DEFAULT_RESIDUAL_TARGET = 1e-5


class ConvergenceMonitorWidget(QWidget):
    """Monitor de convergência em tempo real acoplado à aba de simulação."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Variable", "Current", "Status"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget { gridline-color: #e0e0e0; border: none; border-left: 1px solid #e0e0e0; border-radius: 0; font-size: 8.5pt; }"
            "QHeaderView::section { background-color: #e0e0e0; border: none; border-bottom: 1px solid #c6c6c6; font-weight: 600; padding: 4px; }"
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

        if abs(val) < 1e-3 or abs(val) > 1e4:
            fmt_val = f"{val:.3e}"
        else:
            fmt_val = f"{val:.4f}"

        item_val = QTableWidgetItem(fmt_val)
        target = foamdict.match_residual_target(
            self.targets, name, DEFAULT_RESIDUAL_TARGET
        )

        item_status = QTableWidgetItem()

        is_co = "co" in name.lower() or "courant" in name.lower()
        if is_co and val > 1.0:
            item_val.setForeground(QColor("#b28600"))
            item_status.setText("Warning")
            item_status.setForeground(QColor("#b28600"))
            item_val.setToolTip("High Courant number (> 1.0)")
        elif val <= target:
            item_val.setForeground(QColor("#137333"))
            item_status.setText("Converged")
            item_status.setForeground(QColor("#137333"))
            item_val.setToolTip("Converged!")
        else:
            item_val.setForeground(QColor("#0f62fe"))
            item_status.setText("Iterating")
            item_status.setForeground(QColor("#0f62fe"))
            item_val.setToolTip("Calculating...")

        self.table.setItem(row, 1, item_val)
        self.table.setItem(row, 2, item_status)

    def _row_for(self, name):
        """Índice da linha da variável, criando-a se ainda não existir."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.text() == name:
                return row

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        return row


def format_clean_val(raw_val):
    """Formata valores numéricos de forma limpa, sem zeros excedentes e preservando notação científica."""
    if raw_val is None:
        return ""
    s = str(raw_val).strip()
    if not s:
        return ""
    try:
        float(s)
        if "e" in s.lower():
            return s
        if "." in s:
            s_clean = s.rstrip("0")
            if s_clean.endswith("."):
                s_clean = s_clean[:-1]
            return s_clean
        return s
    except ValueError:
        return s


class CleanTextInput(QLineEdit):
    """Input de texto com linha inferior e destaque azul no foco."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(
            "QLineEdit { background-color: #ffffff; color: #161616; border: none; "
            "border-bottom: 1px solid #8d8d8d; border-radius: 0px; padding: 2px 6px; font-size: 11px; }"
            "QLineEdit:focus { border-bottom: 2px solid #0f62fe; background-color: #ffffff; }"
        )


class CleanNumericInput(CleanTextInput):
    """Input de texto para valores numéricos e notação científica sem zeros extras."""

    def value(self):
        try:
            return float(self.text().strip())
        except (ValueError, TypeError):
            return 0.0

    def setValue(self, val):
        self.setText(format_clean_val(val))


class NoScrollComboBox(QComboBox):
    """QComboBox que ignora a rolagem do mouse quando fechado para evitar alterações acidentais de valor."""

    def wheelEvent(self, event):
        event.ignore()


class ControlDictDockWidget(QDockWidget):
    """Painel lateral dockable para inspecionar e alterar parâmetros do caso (controlDict, parallel, physics, fluid, solvers)."""

    def __init__(self, parent=None):
        super().__init__("Case Settings", parent)
        self.main_window = parent
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setTitleBarWidget(QWidget())

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background-color: #f4f4f4; border: none; }"
            "QWidget#controlDictContainer { background-color: #f4f4f4; }"
            "QGroupBox { font-weight: 600; color: #161616; border: none; border-top: 1px solid #e0e0e0; margin-top: 10px; padding-top: 8px; border-radius: 0; font-size: 11px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 0px; padding: 0 4px; }"
            "QLabel { background-color: transparent; color: #161616; font-size: 11px; }"
            "QComboBox { background-color: #ffffff; color: #161616; border: 1px solid #8d8d8d; padding: 2px 6px; font-size: 11px; border-radius: 0; }"
            "QPushButton { background-color: #ffffff; color: #161616; border: 1px solid #8d8d8d; font-weight: 500; font-size: 11px; padding: 3px 6px; border-radius: 0; }"
            "QPushButton:hover { background-color: #e0e0e0; border-color: #161616; }"
            "QCheckBox { font-size: 11px; color: #161616; background: transparent; }"
        )

        container = QWidget()
        container.setObjectName("controlDictContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 8, 10, 12)
        layout.setSpacing(6)

        # ── Seção 1: Time & Run Controls (controlDict) ──
        self.group_time = QGroupBox("Time && Run Controls", container)
        form_time = QFormLayout(self.group_time)
        form_time.setLabelAlignment(Qt.AlignLeft)
        form_time.setHorizontalSpacing(10)
        form_time.setVerticalSpacing(5)

        self.txt_app = QLabel("-")
        self.txt_app.setStyleSheet("font-weight: 600; color: #0f62fe; font-size: 11px;")
        form_time.addRow("application", self.txt_app)

        self.input_start_from = CleanTextInput()
        form_time.addRow("startFrom", self.input_start_from)

        self.input_start_time = CleanNumericInput()
        form_time.addRow("startTime", self.input_start_time)

        self.input_stop_at = CleanTextInput()
        form_time.addRow("stopAt", self.input_stop_at)

        self.input_end_time = CleanNumericInput()
        self.spin_endtime = self.input_end_time
        form_time.addRow("endTime", self.input_end_time)

        self.input_delta_t = CleanNumericInput()
        self.spin_deltat = self.input_delta_t
        form_time.addRow("deltaT", self.input_delta_t)

        self.input_write_control = CleanTextInput()
        form_time.addRow("writeControl", self.input_write_control)

        self.input_write_interval = CleanNumericInput()
        self.spin_interval = self.input_write_interval
        form_time.addRow("writeInterval", self.input_write_interval)

        self.input_purge_write = CleanNumericInput()
        form_time.addRow("purgeWrite", self.input_purge_write)

        self.input_adjust_time_step = CleanTextInput()
        form_time.addRow("adjustTimeStep", self.input_adjust_time_step)

        self.input_max_co = CleanNumericInput()
        form_time.addRow("maxCo", self.input_max_co)
        layout.addWidget(self.group_time)

        # ── Seção 2: Parallel Execution (decomposeParDict) ──
        self.group_parallel = QGroupBox("Parallel Execution", container)
        form_par = QFormLayout(self.group_parallel)
        form_par.setLabelAlignment(Qt.AlignLeft)
        form_par.setHorizontalSpacing(10)
        form_par.setVerticalSpacing(5)

        sub_layout = QHBoxLayout()
        self.input_subdomains = CleanNumericInput()
        self.input_subdomains.setText("4")
        self.btn_detect_cores = QPushButton("CPU Cores")
        self.btn_detect_cores.setToolTip("Detect number of CPU threads automatically")
        self.btn_detect_cores.clicked.connect(self._auto_detect_cpu_cores)
        sub_layout.addWidget(self.input_subdomains, 1)
        sub_layout.addWidget(self.btn_detect_cores)
        form_par.addRow("Subdomains:", sub_layout)

        self.combo_decomp_method = NoScrollComboBox()
        for meth in ("scotch", "hierarchical", "simple", "kahip"):
            self.combo_decomp_method.addItem(meth, meth)
        form_par.addRow("Method:", self.combo_decomp_method)
        layout.addWidget(self.group_parallel)

        # ── Seção 3: Turbulence & Physics ──
        self.group_turb = QGroupBox("Turbulence && Physics", container)
        form_turb = QFormLayout(self.group_turb)
        form_turb.setLabelAlignment(Qt.AlignLeft)
        form_turb.setHorizontalSpacing(10)
        form_turb.setVerticalSpacing(5)

        self.combo_sim_type = NoScrollComboBox()
        self.combo_sim_type.addItem("RAS (RANS)", "RAS")
        self.combo_sim_type.addItem("LES", "LES")
        self.combo_sim_type.addItem("laminar", "laminar")
        self.combo_sim_type.currentIndexChanged.connect(self._on_sim_type_changed)
        form_turb.addRow("Simulation:", self.combo_sim_type)

        self.combo_turb_model = NoScrollComboBox()
        for m in ("kOmegaSST", "kEpsilon", "SpalartAllmaras", "realizableKE", "rngKE", "WALE", "Smagorinsky"):
            self.combo_turb_model.addItem(m, m)
        form_turb.addRow("Model:", self.combo_turb_model)

        self.chk_turbulence = QCheckBox("Enable Turbulence")
        self.chk_turbulence.setChecked(True)
        form_turb.addRow("", self.chk_turbulence)
        layout.addWidget(self.group_turb)

        # ── Seção 4: Fluid Properties (transportProperties) ──
        self.group_fluid = QGroupBox("Fluid Properties", container)
        form_fluid = QFormLayout(self.group_fluid)
        form_fluid.setLabelAlignment(Qt.AlignLeft)
        form_fluid.setHorizontalSpacing(10)
        form_fluid.setVerticalSpacing(5)

        self.combo_fluid_preset = NoScrollComboBox()
        self.combo_fluid_preset.addItem("Water (20°C)", "water")
        self.combo_fluid_preset.addItem("Air (20°C)", "air")
        self.combo_fluid_preset.addItem("Engine Oil", "oil")
        self.combo_fluid_preset.addItem("Blood (CFD)", "blood")
        self.combo_fluid_preset.addItem("Custom", "custom")
        self.combo_fluid_preset.currentIndexChanged.connect(self._on_fluid_preset_changed)
        form_fluid.addRow("Preset:", self.combo_fluid_preset)

        self.input_nu = CleanNumericInput()
        self.input_nu.setText("1e-06")
        form_fluid.addRow("nu (m²/s):", self.input_nu)

        self.input_rho = CleanNumericInput()
        self.input_rho.setText("1000")
        form_fluid.addRow("rho (kg/m³):", self.input_rho)
        layout.addWidget(self.group_fluid)

        # ── Seção 5: Solvers & Relaxation (fvSolution) ──
        self.group_solvers = QGroupBox("Solvers && Numerical Schemes", container)
        form_solvers = QFormLayout(self.group_solvers)
        form_solvers.setLabelAlignment(Qt.AlignLeft)
        form_solvers.setHorizontalSpacing(10)
        form_solvers.setVerticalSpacing(5)

        self.lbl_algorithm = QLabel("PIMPLE")
        self.lbl_algorithm.setStyleSheet("font-weight: 600; color: #161616; font-size: 11px;")
        form_solvers.addRow("Algorithm:", self.lbl_algorithm)

        self.input_relax_p = CleanNumericInput()
        self.input_relax_p.setText("0.3")
        form_solvers.addRow("Relax p:", self.input_relax_p)

        self.input_relax_u = CleanNumericInput()
        self.input_relax_u.setText("0.7")
        form_solvers.addRow("Relax U:", self.input_relax_u)
        layout.addWidget(self.group_solvers)

        # ── Botão Global de Salvamento ──
        layout.addSpacing(6)
        self.btn_save = QPushButton("Save All Settings")
        self.btn_save.setStyleSheet(
            "background-color: #0f62fe; color: #ffffff; font-weight: 600; font-size: 11px; padding: 7px 12px; border: none; border-radius: 0;"
        )
        self.btn_save.clicked.connect(self.save_parameters)
        layout.addWidget(self.btn_save)
        layout.addSpacing(10)

        layout.addStretch(1)
        scroll.setWidget(container)
        self.setWidget(scroll)

        self.current_case_path = None
        self.setEnabled(False)

    def _auto_detect_cpu_cores(self):
        try:
            import multiprocessing
            count = multiprocessing.cpu_count()
        except Exception:
            count = os.cpu_count() or 4
        self.input_subdomains.setText(str(count))

    def _on_sim_type_changed(self, idx):
        sim_type = self.combo_sim_type.currentData()
        self.combo_turb_model.setEnabled(sim_type != "laminar")
        self.chk_turbulence.setEnabled(sim_type != "laminar")

    def _on_fluid_preset_changed(self, idx):
        preset = self.combo_fluid_preset.currentData()
        if preset == "water":
            self.input_nu.setText("1.004e-06")
            self.input_rho.setText("998.2")
        elif preset == "air":
            self.input_nu.setText("1.516e-05")
            self.input_rho.setText("1.204")
        elif preset == "oil":
            self.input_nu.setText("2.0e-04")
            self.input_rho.setText("880.0")
        elif preset == "blood":
            self.input_nu.setText("3.3e-06")
            self.input_rho.setText("1060.0")

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
        # 1. controlDict
        self.txt_app.setText(params.get("application", "-"))
        self.input_start_from.setText(params.get("startFrom", ""))
        self.input_start_time.setText(format_clean_val(params.get("startTime", "")))
        self.input_stop_at.setText(params.get("stopAt", ""))
        self.input_end_time.setText(format_clean_val(params.get("endTime", "")))
        self.input_delta_t.setText(format_clean_val(params.get("deltaT", "")))
        self.input_write_control.setText(params.get("writeControl", ""))
        self.input_write_interval.setText(format_clean_val(params.get("writeInterval", "")))
        self.input_purge_write.setText(format_clean_val(params.get("purgeWrite", "")))
        self.input_adjust_time_step.setText(params.get("adjustTimeStep", ""))
        self.input_max_co.setText(format_clean_val(params.get("maxCo", "")))

        # 2. decomposeParDict
        par_params = foamdict.read_decompose_par_dict(case_path)
        self.input_subdomains.setText(par_params.get("numberOfSubdomains", "4"))
        meth = par_params.get("method", "scotch")
        idx_meth = self.combo_decomp_method.findData(meth)
        if idx_meth != -1:
            self.combo_decomp_method.setCurrentIndex(idx_meth)

        # 3. turbulenceProperties
        turb_params = foamdict.read_turbulence_properties(case_path)
        sim_t = turb_params.get("simulationType", "RAS")
        idx_sim = self.combo_sim_type.findData(sim_t)
        if idx_sim != -1:
            self.combo_sim_type.setCurrentIndex(idx_sim)
            
        mod = turb_params.get("model", "kOmegaSST")
        idx_mod = self.combo_turb_model.findData(mod)
        if idx_mod != -1:
            self.combo_turb_model.setCurrentIndex(idx_mod)
        else:
            self.combo_turb_model.insertItem(0, mod, mod)
            self.combo_turb_model.setCurrentIndex(0)
        self.chk_turbulence.setChecked(turb_params.get("turbulence", "on").lower() == "on")

        # 4. transportProperties
        trans_params = foamdict.read_transport_properties(case_path)
        self.input_nu.setText(format_clean_val(trans_params.get("nu", "1e-05")))
        self.input_rho.setText(format_clean_val(trans_params.get("rho", "1000")))

        # 5. fvSolution
        sol_data = foamdict.read_fv_solution(case_path)
        algo = sol_data.get("algorithm", "SIMPLE")
        self.lbl_algorithm.setText(algo if algo else "-")
        rel_fields = sol_data.get("relaxation_fields", {})
        rel_eqs = sol_data.get("relaxation_equations", {})
        if "p" in rel_fields:
            self.input_relax_p.setText(format_clean_val(rel_fields["p"]))
        elif "p" in rel_eqs:
            self.input_relax_p.setText(format_clean_val(rel_eqs["p"]))
            
        if "U" in rel_fields:
            self.input_relax_u.setText(format_clean_val(rel_fields["U"]))
        elif "U" in rel_eqs:
            self.input_relax_u.setText(format_clean_val(rel_eqs["U"]))

    def save_parameters(self):
        if not self.current_case_path:
            return

        # 1. Salva controlDict
        values = {}
        fields = {
            "startFrom": self.input_start_from.text().strip(),
            "startTime": self.input_start_time.text().strip(),
            "stopAt": self.input_stop_at.text().strip(),
            "endTime": self.input_end_time.text().strip(),
            "deltaT": self.input_delta_t.text().strip(),
            "writeControl": self.input_write_control.text().strip(),
            "writeInterval": self.input_write_interval.text().strip(),
            "purgeWrite": self.input_purge_write.text().strip(),
            "adjustTimeStep": self.input_adjust_time_step.text().strip(),
            "maxCo": self.input_max_co.text().strip(),
        }
        for k, v in fields.items():
            if v != "":
                values[k] = v
        foamdict.write_control_dict(self.current_case_path, values)

        # 2. Salva decomposeParDict
        par_vals = {
            "numberOfSubdomains": self.input_subdomains.text().strip() or "4",
            "method": self.combo_decomp_method.currentData() or "scotch",
        }
        foamdict.write_decompose_par_dict(self.current_case_path, par_vals)

        # 3. Salva turbulenceProperties
        turb_vals = {
            "simulationType": self.combo_sim_type.currentData() or "RAS",
            "model": self.combo_turb_model.currentText().strip() or "kOmegaSST",
            "turbulence": "on" if self.chk_turbulence.isChecked() else "off",
        }
        foamdict.write_turbulence_properties(self.current_case_path, turb_vals)

        # 4. Salva transportProperties
        trans_vals = {
            "nu": self.input_nu.text().strip() or "1e-05",
            "rho": self.input_rho.text().strip() or "1000",
        }
        foamdict.write_transport_properties(self.current_case_path, trans_vals)

        # 5. Salva fvSolution
        p_val = self.input_relax_p.text().strip()
        u_val = self.input_relax_u.text().strip()
        relax_f = {}
        if p_val:
            try: relax_f["p"] = float(p_val)
            except ValueError: pass
        if u_val:
            try: relax_f["U"] = float(u_val)
            except ValueError: pass
        if relax_f:
            foamdict.write_fv_solution_params(self.current_case_path, relaxation_fields=relax_f)

        QMessageBox.information(self, "Success", "All case settings saved successfully!")
        if hasattr(self.main_window, "log"):
            self.main_window.log("Case configuration settings saved.\n")
        self._reload_open_editor()

    def _reload_open_editor(self):
        """Recarrega os dicionários abertos no editor caso estejam em abas."""
        if not self.current_case_path:
            return
        editors = getattr(self.main_window, "path_to_editor", None)
        if not editors:
            return
        for dname in ("system/controlDict", "system/decomposeParDict", "system/fvSolution", "constant/turbulenceProperties", "constant/transportProperties"):
            dpath = os.path.join(self.current_case_path, dname)
            editor = editors.get(dpath)
            if editor is not None and os.path.isfile(dpath):
                try:
                    with open(dpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    editor.blockSignals(True)
                    editor.setPlainText(content)
                    editor.blockSignals(False)
                except OSError:
                    pass



# ---------------------------------------------------------------------------
# Discretisation Schemes dock (Feature 4)
# ---------------------------------------------------------------------------

# Preset choices for each scheme block.
_SCHEME_OPTIONS = {
    "ddtSchemes": ["Euler", "backward", "CrankNicolson 0.9", "steadyState", "localEuler"],
    "gradSchemes": ["Gauss linear", "leastSquares", "Gauss linear corrected"],
    "divSchemes": [
        "none", "Gauss upwind", "Gauss linearUpwind grad(U)",
        "Gauss vanLeer", "Gauss limitedLinear 1", "Gauss linear",
        "bounded Gauss linearUpwind grad(U)",
    ],
    "laplacianSchemes": [
        "Gauss linear corrected", "Gauss linear uncorrected",
        "Gauss linear limited corrected 0.5",
    ],
    "interpolationSchemes": ["linear", "midPoint", "upwind"],
    "snGradSchemes": ["corrected", "uncorrected", "limited corrected 0.5"],
}


class NoScrollComboBox(QComboBox):
    """QComboBox que ignora a rolagem do mouse quando fechado para evitar alterações acidentais de valor."""

    def wheelEvent(self, event):
        event.ignore()


class FvSchemesDockWidget(QDockWidget):
    """Dock widget for visual editing of ``system/fvSchemes``."""

    def __init__(self, parent=None):
        super().__init__("fvSchemes", parent)
        self.main_window = parent
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setTitleBarWidget(QWidget())

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #f4f4f4; border: none; }")

        container = QWidget()
        container.setObjectName("fvSchemesContainer")
        container.setStyleSheet("QWidget#fvSchemesContainer { background-color: #f4f4f4; }")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("fvSchemes")
        header.setStyleSheet("font-weight: 700; color: #161616; font-size: 13px;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self._combos = {}
        for block_name, options in _SCHEME_OPTIONS.items():
            label = block_name.replace("Schemes", "")
            combo = NoScrollComboBox()
            combo.setEditable(True)
            combo.addItems(options)
            combo.setStyleSheet(
                "QComboBox { background-color: #ffffff; color: #161616; border: none; "
                "border-bottom: 1px solid #8d8d8d; border-radius: 0px; padding: 2px 6px; font-size: 11px; }"
                "QComboBox:focus { border-bottom: 2px solid #0f62fe; }"
            )
            form.addRow(label, combo)
            self._combos[block_name] = combo


        layout.addLayout(form)

        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setStyleSheet(
            "background-color: #0f62fe; color: #ffffff; font-weight: 600; font-size: 11px; "
            "padding: 4px 10px; border: none; border-radius: 0;"
        )
        self.btn_save.clicked.connect(self.save_schemes)
        layout.addWidget(self.btn_save)

        layout.addStretch(1)
        scroll.setWidget(container)
        self.setWidget(scroll)

        self.current_case_path = None
        self.setEnabled(False)

    def load_case(self, case_path):
        self.current_case_path = case_path
        if not case_path:
            self.setEnabled(False)
            return
        schemes = foamdict.read_fv_schemes(case_path)
        if not schemes:
            self.setEnabled(False)
            return
        self.setEnabled(True)
        for block_name, combo in self._combos.items():
            val = schemes.get(block_name, "")
            if val:
                idx = combo.findText(val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(val)

    def save_schemes(self):
        if not self.current_case_path:
            return
        values = {}
        for block_name, combo in self._combos.items():
            text = combo.currentText().strip()
            if text:
                values[block_name] = text
        if not foamdict.write_fv_schemes(self.current_case_path, values):
            QMessageBox.critical(self, "Error", "Failed to update fvSchemes.")
            return
        QMessageBox.information(self, "Success", "fvSchemes saved successfully!")
        if hasattr(self.main_window, "log"):
            self.main_window.log("fvSchemes parameters updated.\n")
        self._reload_open_editor("fvSchemes")

    def _reload_open_editor(self, dict_name):
        dict_path = os.path.join(self.current_case_path, "system", dict_name)
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


# ---------------------------------------------------------------------------
# Solver / Algorithm dock (Feature 4)
# ---------------------------------------------------------------------------

class FvSolutionDockWidget(QDockWidget):
    """Dock widget for visual editing of ``system/fvSolution`` algorithm and relaxation."""

    def __init__(self, parent=None):
        super().__init__("fvSolution", parent)
        self.main_window = parent
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setTitleBarWidget(QWidget())

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #f4f4f4; border: none; }")

        container = QWidget()
        container.setObjectName("fvSolutionContainer")
        container.setStyleSheet("QWidget#fvSolutionContainer { background-color: #f4f4f4; }")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("fvSolution")
        header.setStyleSheet("font-weight: 700; color: #161616; font-size: 13px;")
        layout.addWidget(header)

        # Algorithm section
        algo_lbl = QLabel("Algorithm")
        algo_lbl.setStyleSheet("font-weight: 600; color: #161616; font-size: 11px;")
        layout.addWidget(algo_lbl)

        self.txt_algo = QLabel("-")
        self.txt_algo.setStyleSheet("color: #0f62fe; font-weight: 600; font-size: 11px;")
        layout.addWidget(self.txt_algo)

        algo_form = QFormLayout()
        algo_form.setLabelAlignment(Qt.AlignLeft)
        algo_form.setHorizontalSpacing(14)
        algo_form.setVerticalSpacing(8)

        self.input_n_correctors = CleanNumericInput()
        algo_form.addRow("nCorrectors", self.input_n_correctors)

        self.input_n_non_ortho = CleanNumericInput()
        algo_form.addRow("nNonOrthogonal", self.input_n_non_ortho)

        self.input_n_outer = CleanNumericInput()
        algo_form.addRow("nOuterCorrectors", self.input_n_outer)

        layout.addLayout(algo_form)

        # Relaxation Factors section
        relax_lbl = QLabel("Relaxation Factors")
        relax_lbl.setStyleSheet("font-weight: 600; color: #161616; font-size: 11px; margin-top: 8px;")
        layout.addWidget(relax_lbl)

        self.relax_table = QTableWidget()
        self.relax_table.setColumnCount(3)
        self.relax_table.setHorizontalHeaderLabels(["Category", "Field", "Factor"])
        rh = self.relax_table.horizontalHeader()
        rh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        rh.setSectionResizeMode(1, QHeaderView.Stretch)
        rh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.relax_table.setStyleSheet(
            "QTableWidget { gridline-color: #e0e0e0; border: none; border-radius: 0; font-size: 11px; }"
            "QHeaderView::section { background-color: #e0e0e0; border: none; "
            "border-bottom: 1px solid #c6c6c6; font-weight: 600; padding: 3px 6px; font-size: 11px; }"
        )
        self.relax_table.setMaximumHeight(200)
        layout.addWidget(self.relax_table)

        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setStyleSheet(
            "background-color: #0f62fe; color: #ffffff; font-weight: 600; font-size: 11px; "
            "padding: 4px 10px; border: none; border-radius: 0;"
        )
        self.btn_save.clicked.connect(self.save_solution)
        layout.addWidget(self.btn_save)


        layout.addStretch(1)
        scroll.setWidget(container)
        self.setWidget(scroll)

        self.current_case_path = None
        self.setEnabled(False)

    def load_case(self, case_path):
        self.current_case_path = case_path
        if not case_path:
            self.setEnabled(False)
            return
        data = foamdict.read_fv_solution(case_path)
        if not data:
            self.setEnabled(False)
            return
        self.setEnabled(True)

        self.txt_algo.setText(data.get("algorithm", "-"))
        params = data.get("algorithm_params", {})
        self.input_n_correctors.setValue(params.get("nCorrectors", ""))
        self.input_n_non_ortho.setValue(params.get("nNonOrthogonalCorrectors", ""))
        self.input_n_outer.setValue(params.get("nOuterCorrectors", ""))

        # Relaxation factors table
        rf = data.get("relaxation_fields", {})
        re_eq = data.get("relaxation_equations", {})
        total_rows = len(rf) + len(re_eq)
        self.relax_table.setRowCount(total_rows)
        row = 0
        for field, factor in rf.items():
            self.relax_table.setItem(row, 0, QTableWidgetItem("fields"))
            self.relax_table.setItem(row, 1, QTableWidgetItem(field))
            item = QTableWidgetItem(str(factor))
            self.relax_table.setItem(row, 2, item)
            row += 1
        for eq, factor in re_eq.items():
            self.relax_table.setItem(row, 0, QTableWidgetItem("equations"))
            self.relax_table.setItem(row, 1, QTableWidgetItem(eq))
            item = QTableWidgetItem(str(factor))
            self.relax_table.setItem(row, 2, item)
            row += 1

    def save_solution(self):
        if not self.current_case_path:
            return
        algo_params = {}
        v = self.input_n_correctors.text().strip()
        if v:
            algo_params["nCorrectors"] = v
        v = self.input_n_non_ortho.text().strip()
        if v:
            algo_params["nNonOrthogonalCorrectors"] = v
        v = self.input_n_outer.text().strip()
        if v:
            algo_params["nOuterCorrectors"] = v

        relax_f = {}
        relax_e = {}
        for row in range(self.relax_table.rowCount()):
            cat_item = self.relax_table.item(row, 0)
            name_item = self.relax_table.item(row, 1)
            val_item = self.relax_table.item(row, 2)
            if not cat_item or not name_item or not val_item:
                continue
            cat = cat_item.text()
            name = name_item.text()
            val = val_item.text()
            if cat == "fields":
                relax_f[name] = val
            else:
                relax_e[name] = val

        if not foamdict.write_fv_solution_params(
            self.current_case_path, algo_params, relax_f, relax_e
        ):
            QMessageBox.critical(self, "Error", "Failed to update fvSolution.")
            return
        QMessageBox.information(self, "Success", "fvSolution saved successfully!")
        if hasattr(self.main_window, "log"):
            self.main_window.log("fvSolution parameters updated.\n")
        self._reload_open_editor()

    def _reload_open_editor(self):
        dict_path = os.path.join(self.current_case_path, "system", "fvSolution")
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
