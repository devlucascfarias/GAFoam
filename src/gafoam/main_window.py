"""Janela principal da aplicação: layout, execução de comandos e monitoramento."""

import os
import shutil
import signal
import stat
import subprocess
import time

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QMenu,
    QSplitter,
    QTabWidget,
    QTabBar,
    QFileDialog,
    QMessageBox,
    QToolBar,
    QLabel,
    QProgressBar,
    QToolButton,
)

from PySide6.QtGui import QAction, QIcon, QFont, QKeySequence, QPalette, QColor, QTextCursor, QPixmap
from PySide6.QtCore import QProcess, Qt, QSize, QTimer

from gafoam import foamdict, logparse
from gafoam.bc_editor import BoundaryConditionEditor
from gafoam.editor import EditorContainerWidget, SimpleHighlighter
from gafoam.filebrowser import FileBrowser
from gafoam.handlers import make_stdout_handler, make_stderr_handler, make_finished_handler
from gafoam.menus import setup_menus
from gafoam.panels import (
    ControlDictDockWidget,
    ConvergenceMonitorWidget,
    FvSchemesDockWidget,
    FvSolutionDockWidget,
)
from gafoam.report import ReportGenerator
from gafoam.residuals import ResidualsWidget
from gafoam.resources import icon_path, load_application_fonts
from gafoam.stl_viewer import CaseGeometryWidget



class WelcomeWidget(QWidget):
    """Tela inicial de boas-vindas exibida quando nenhum caso está aberto."""

    def __init__(self, on_upload_clicked=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        center_box = QWidget()
        box_layout = QVBoxLayout(center_box)
        box_layout.setAlignment(Qt.AlignCenter)
        box_layout.setSpacing(14)

        title = QLabel("Welcome again!")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "QLabel { font-size: 26px; font-weight: 600; color: #161616; background: transparent; }"
        )
        box_layout.addWidget(title)

        desc = QLabel(
            "Upload an OpenFOAM case directory to manage dictionaries,\n"
            "inspect mesh geometry, monitor solver residuals, and run simulations."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(
            "QLabel { font-size: 13px; color: #525252; line-height: 1.5; background: transparent; }"
        )
        box_layout.addWidget(desc)

        box_layout.addSpacing(8)

        btn_upload = QPushButton("Upload the OpenFOAM Case")
        icon = icon_path("open_case.svg")
        if os.path.isfile(icon):
            btn_upload.setIcon(QIcon(icon))
            btn_upload.setIconSize(QSize(16, 16))
        btn_upload.setStyleSheet(
            "QPushButton { background-color: #0f62fe; color: #ffffff; font-weight: 400; "
            "font-size: 12px; padding: 8px 18px; border: none; border-radius: 0px; } "
            "QPushButton:hover { background-color: #0353e9; } "
            "QPushButton:pressed { background-color: #002d9c; }"
        )
        btn_upload.setCursor(Qt.PointingHandCursor)
        if on_upload_clicked:
            btn_upload.clicked.connect(on_upload_clicked)
        box_layout.addWidget(btn_upload, alignment=Qt.AlignCenter)

        layout.addWidget(center_box)


class PermanentFirstTabWidget(QTabWidget):
    """QTabWidget onde a primeira aba 'Geometry' é permanente e nunca possui botão de fechar."""

    def tabInserted(self, index):
        super().tabInserted(index)
        for i in range(self.count()):
            if self.tabText(i) == "Geometry":
                self.tabBar().setTabButton(i, QTabBar.RightSide, None)
                self.tabBar().setTabButton(i, QTabBar.LeftSide, None)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GAFoam - OpenFOAM GUI")
        self.resize(1380, 850)
        self.setMinimumSize(950, 600)

        # Registra e define o ícone oficial da janela do GAFoam
        app_icon = icon_path("gafoam_logo.svg")
        if os.path.isfile(app_icon):
            self.setWindowIcon(QIcon(app_icon))

        self.editor_tabs = PermanentFirstTabWidget(self)
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self.on_tab_close_requested)

        self.welcome_widget = WelcomeWidget(on_upload_clicked=self.selecionar_caso, parent=self)
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self.welcome_widget)
        self.editor_stack.addWidget(self.editor_tabs)
        self.editor_stack.setCurrentWidget(self.welcome_widget)

        self.geom_view = CaseGeometryWidget(parent=self)
        self.geom_scanned_case = None

        self.path_to_editor = {}
        self.editor_to_path = {}

        self.current_case = None

        self.tab_widget = QTabWidget()
        
        # 1. Console de Execução (logs da interface e saída padrão de comandos)
        self.console_view = QTextEdit(parent=self)
        self.console_view.setReadOnly(True)
        self.console_view.setStyleSheet(
            "QTextEdit { font-family: 'Fira Code', 'IBM Plex Mono', 'Consolas', monospace; "
            "font-size: 13px; line-height: 1.5; border: none; padding: 12px; "
            "background-color: #262626; color: #c6c6c6; }"
        )
        self.tab_widget.addTab(self.console_view, "Console")

        # 2. Simulação (Visualização do Solver com Monitor de Convergência acoplado)
        # 2. Simulation (Solver Output + Convergence Monitor)
        sim_container = QWidget(parent=self)
        sim_layout = QVBoxLayout(sim_container)
        sim_layout.setContentsMargins(0, 0, 0, 0)
        sim_layout.setSpacing(0)

        self.divergence_banner = QLabel(self)
        self.divergence_banner.setStyleSheet(
            "QLabel { background-color: #fff1f1; color: #da1e28; font-weight: 600; "
            "border-bottom: 1px solid #da1e28; padding: 6px 12px; font-size: 11px; }"
        )
        self.divergence_banner.setVisible(False)
        sim_layout.addWidget(self.divergence_banner)

        self.sim_log_view = QTextEdit(parent=self)
        self.sim_log_view.setReadOnly(True)
        self.sim_log_view.setStyleSheet(
            "QTextEdit { font-family: 'Fira Code', 'IBM Plex Mono', 'Consolas', monospace; "
            "font-size: 13px; line-height: 1.5; border: none; padding: 12px; "
            "background-color: #262626; color: #c6c6c6; }"
        )

        self.convergence_monitor = ConvergenceMonitorWidget(parent=self)
        self.convergence_monitor.setStyleSheet("background-color: #f4f4f4; border-left: 1px solid #e0e0e0;")

        self.sim_splitter = QSplitter(Qt.Horizontal, parent=sim_container)
        self.sim_splitter.addWidget(self.sim_log_view)
        self.sim_splitter.addWidget(self.convergence_monitor)
        self.sim_splitter.setStretchFactor(0, 1)
        self.sim_splitter.setStretchFactor(1, 1)
        self.sim_splitter.setSizes([450, 450])
        sim_layout.addWidget(self.sim_splitter)

        self.tab_widget.addTab(sim_container, "Simulation")

        # 3. Condições de Contorno (0/ boundaryField Editor)
        self.bc_editor = BoundaryConditionEditor(parent=self)
        self.tab_widget.addTab(self.bc_editor, "Boundary Conditions")

        self.residuals_view = ResidualsWidget(parent=self)

        self.top_splitter = QSplitter(Qt.Horizontal)
        self.top_splitter.addWidget(self.editor_stack)
        self.top_splitter.addWidget(self.residuals_view)
        self.top_splitter.setStretchFactor(0, 3)
        self.top_splitter.setStretchFactor(1, 2)
        self.residuals_view.setVisible(False) # Hide initially

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self.top_splitter)
        right_splitter.addWidget(self.tab_widget)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)

        setup_menus(self)

        # 4. Dock Widget para controlDict (Parâmetros do Caso)
        self.control_dock = ControlDictDockWidget(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.control_dock)

        # 5. Dock Widget para fvSchemes (Esquemas Numéricos)
        self.fv_schemes_dock = FvSchemesDockWidget(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.fv_schemes_dock)

        # 6. Dock Widget para fvSolution (Algoritmo e Relaxação)
        self.fv_solution_dock = FvSolutionDockWidget(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.fv_solution_dock)
        
        # Sincroniza os toggleViewAction com o menu "View"
        toggle_dock_act = self.control_dock.toggleViewAction()
        toggle_dock_act.setText("controlDict")
        
        toggle_schemes_act = self.fv_schemes_dock.toggleViewAction()
        toggle_schemes_act.setText("fvSchemes")

        toggle_solution_act = self.fv_solution_dock.toggleViewAction()
        toggle_solution_act.setText("fvSolution")

        view_menu = None
        for action in self.menuBar().actions():
            if action.text() in ("View", "Exibir"):
                view_menu = action.menu()
                break
        if not view_menu:
            view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(toggle_dock_act)
        view_menu.addAction(toggle_schemes_act)
        view_menu.addAction(toggle_solution_act)

        try:
            self.toolbar = QToolBar("GAFoam")
            self.toolbar.setMovable(False)
            self.toolbar.setFloatable(False)
            self.toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self.toolbar.setIconSize(QSize(0, 0))
            self.addToolBar(self.toolbar)

            # Apenas o Ícone CFD no header (fundo 100% transparente, sem texto nem caixas brancas)
            logo_icon = QLabel()
            icon_p = icon_path("gafoam_logo.svg")
            if os.path.isfile(icon_p):
                pm = QPixmap(icon_p).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                logo_icon.setPixmap(pm)
            logo_icon.setStyleSheet("QLabel { background: transparent; padding: 2px 14px 2px 4px; border: none; }")
            self.toolbar.addWidget(logo_icon)

            case_act = QAction('Open Case', self)
            case_act.setToolTip('Open Case')
            case_act.setStatusTip('Select OpenFOAM case directory')
            case_act.triggered.connect(self.selecionar_caso)
            self.toolbar.addAction(case_act)

            self.run_action = QAction('Run', self)
            self.run_action.setToolTip('Run (Ctrl+R)')
            self.run_action.setStatusTip('Run simulation (Allrun)')
            self.run_action.setShortcut(QKeySequence('Ctrl+R'))
            self.run_action.triggered.connect(self.run_simulation)
            self.toolbar.addAction(self.run_action)

            self.pause_action = QAction('Pause', self)
            self.pause_action.setToolTip('Pause / Resume Simulation')
            self.pause_action.setStatusTip('Pause or resume running process')
            self.pause_action.triggered.connect(self.toggle_pause_simulation)
            self.pause_action.setEnabled(False)
            self.toolbar.addAction(self.pause_action)

            self.stop_action = QAction('Stop', self)
            self.stop_action.setToolTip('Stop Simulation')
            self.stop_action.setStatusTip('Stop running process completely')
            self.stop_action.triggered.connect(self.stop_process)
            self.stop_action.setEnabled(False)
            self.toolbar.addAction(self.stop_action)

            self.paraview_action = QAction('Open in ParaView', self)
            self.paraview_action.setToolTip('Open Case in ParaView')
            self.paraview_action.setStatusTip('Launch ParaView to visualize fields')
            self.paraview_action.triggered.connect(self.open_paraview)
            self.toolbar.addAction(self.paraview_action)
        except Exception:
            pass

        try:
            # Botão de dropdown para OpenFOAM Tools (estilo Carbon Shell)
            self.util_btn = QToolButton(self)
            self.util_btn.setText("OpenFOAM Tools")
            self.util_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self.util_btn.setPopupMode(QToolButton.InstantPopup)
            self.util_btn.setStyleSheet(
                "QToolButton::menu-indicator { image: none; }"
            )


            util_menu = QMenu(self)
            cmd_icon = self._load_svg_icon('cmd_dollar.svg', 'utilities-terminal')

            actions = []

            block_act = QAction(cmd_icon, 'blockMesh', self)
            block_act.setStatusTip('Executar blockMesh')
            block_act.triggered.connect(self.run_blockMesh)
            actions.append(block_act)

            check_act = QAction(cmd_icon, 'checkMesh', self)
            check_act.setStatusTip('Executar checkMesh')
            check_act.triggered.connect(self.run_checkMesh)
            actions.append(check_act)

            snappy_act = QAction(cmd_icon, 'snappyHexMesh', self)
            snappy_act.setStatusTip('Executar snappyHexMesh')
            snappy_act.triggered.connect(self.run_snappyHexMesh)
            actions.append(snappy_act)

            decomp_act = QAction(cmd_icon, "decomposePar", self)
            decomp_act.triggered.connect(self.run_decomposePar)
            actions.append(decomp_act)

            recon_act = QAction(cmd_icon, "reconstructPar", self)
            recon_act.triggered.connect(self.run_reconstructPar)
            actions.append(recon_act)

            yplus_act = QAction(cmd_icon, "yPlus", self)
            yplus_act.triggered.connect(self.run_yPlus)
            actions.append(yplus_act)

            clean_act = QAction(cmd_icon, "Allclean", self)
            clean_act.triggered.connect(self.run_allclean)
            actions.append(clean_act)

            verify_act = QAction(cmd_icon, 'Verify Case (Pre-flight)', self)
            verify_act.setStatusTip('Run global pre-flight verification on current case')
            verify_act.triggered.connect(self.verify_current_case)
            actions.append(verify_act)

            report_act = QAction(cmd_icon, 'Export Report (PDF)', self)
            report_act.setStatusTip('Generate PDF simulation report')
            report_act.triggered.connect(self.export_report)
            actions.append(report_act)

            for act in actions:
                act.setIconVisibleInMenu(True)

            util_menu.addAction(verify_act)
            util_menu.addAction(report_act)
            util_menu.addSeparator()
            util_menu.addAction(block_act)
            util_menu.addAction(check_act)
            util_menu.addAction(snappy_act)
            util_menu.addSeparator()
            util_menu.addAction(decomp_act)
            util_menu.addAction(recon_act)
            util_menu.addAction(yplus_act)
            util_menu.addSeparator()
            util_menu.addAction(clean_act)

            self.util_btn.setMenu(util_menu)
            self.toolbar.addWidget(self.util_btn)

            # Define cursor de mãozinha (PointingHandCursor) em todos os botões do header
            for btn in self.toolbar.findChildren(QToolButton):
                btn.setCursor(Qt.PointingHandCursor)

        except Exception:
            pass

        self.scale = 1


        self.file_browser = FileBrowser(scale=self.scale, parent=self)
        self.file_view = self.file_browser.file_view

        splitter = QSplitter()
        splitter.addWidget(self.file_view)
        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(1, 1)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

        try:
            self.editor_tabs.setMinimumHeight(180)
            self.top_splitter.setSizes([int(self.width() * 0.6), int(self.width() * 0.4)])
            right_splitter.setSizes([int(self.height() * 0.75), int(self.height() * 0.25)])
            splitter.setSizes([int(260 * self.scale), max(200, self.width() - int(260 * self.scale))])
        except Exception:
            pass

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(make_stdout_handler(self))
        self.process.readyReadStandardError.connect(make_stderr_handler(self))
        self.process.finished.connect(make_finished_handler(self))
        try:
            self.process.started.connect(self._on_process_started)
            self.process.finished.connect(self._on_process_finished)
        except Exception:
            pass

        self.file_browser.set_click_callback(self.on_file_clicked)

        self.current_file = None
        self.current_sim_time = 0.0
        self.follow_solver_log = False
        self.log_follow_path = None
        self.log_follow_pos = 0
        self.log_follow_ino = None
        self.log_follow_shown_path = None
        self.detached_run_active = False
        self.detached_last_log_growth = 0.0
        self.detached_stale_seconds = 30.0
        self.log_follow_last_size = 0
        self.is_paused = False
        self.sim_iter_count = 0

        self.log_follow_timer = QTimer(self)
        self.log_follow_timer.setInterval(600)
        self.log_follow_timer.timeout.connect(self._poll_solver_log)

        try:
            self.kpi_time = QLabel("t: --")
            self.kpi_time.setStyleSheet("color: #525252; font-size: 11px; padding: 0 8px;")
            self.kpi_co = QLabel("Co max: --")
            self.kpi_co.setStyleSheet("color: #525252; font-size: 11px; padding: 0 8px;")
            self.kpi_iter = QLabel("Iter: --")
            self.kpi_iter.setStyleSheet("color: #525252; font-size: 11px; padding: 0 8px;")
            self.statusBar().addWidget(self.kpi_time)
            self.statusBar().addWidget(self.kpi_co)
            self.statusBar().addWidget(self.kpi_iter)

            self.status_label = QLabel("Idle")
            self.status_progress = QProgressBar()
            self.status_progress.setFixedWidth(120)
            self.status_progress.setTextVisible(False)
            self.status_progress.setRange(0, 0)  
            self.status_progress.setVisible(False)
            self.statusBar().addPermanentWidget(self.status_label)
            self.statusBar().addPermanentWidget(self.status_progress)
        except Exception:
            pass

        self.apply_light_theme()
        self.apply_scale()

        # Estado inicial (sem caso aberto): oculta os docks e o painel inferior
        self.control_dock.hide()
        self.fv_schemes_dock.hide()
        self.fv_solution_dock.hide()
        self.tab_widget.hide()

    def log(self, text):
        """Adiciona mensagens de log no Console de Execução."""
        if not text:
            return
        try:
            self.console_view.moveCursor(QTextCursor.End)
            self.console_view.insertPlainText(text)
            self.console_view.moveCursor(QTextCursor.End)
        except Exception:
            pass



    def show_tab(self, name):
        """Foca em uma aba específica pelo nome."""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == name:
                self.tab_widget.setCurrentIndex(i)
                break

    def _load_svg_icon(self, filename, fallback_theme=None):
        """Ícone do pacote, com fallback para o tema do sistema."""
        path = icon_path(filename)
        if os.path.isfile(path):
            return QIcon(path)
        if fallback_theme:
            return QIcon.fromTheme(fallback_theme)
        return QIcon()

    def selecionar_caso(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select OpenFOAM Case Directory")
        if not dir_path:
            return
        missing = foamdict.validate_case_dirs(dir_path)
        if missing:
            QMessageBox.critical(self, "Error", f"Selected directory is missing required subdirectories: {', '.join(missing)}")
            return
        self.log(f"Case opened: {dir_path}\n")
        self.file_browser.set_root(dir_path)
        self.current_case = dir_path
        self.geom_scanned_case = None

        self.editor_stack.setCurrentWidget(self.editor_tabs)
        self.control_dock.show()
        self.control_dock.load_case(dir_path)
        self.fv_schemes_dock.load_case(dir_path)
        self.fv_solution_dock.load_case(dir_path)
        self.bc_editor.load_case(dir_path)
        self.convergence_monitor.load_case(dir_path)
        self.tab_widget.show()
        # Sempre abre e exibe o módulo Geometry como aba permanente
        self.show_geometry()

        QMessageBox.information(self, "Success", f"OpenFOAM case opened successfully!\n{dir_path}")

    def on_file_clicked(self, index):

        if not index.isValid():
            return
        if self.file_browser.file_model.isDir(index):
            return
        file_path = self.file_browser.file_model.filePath(index)

        # Se for malha STL/OBJ, abre e destaca diretamente no visualizador 3D
        if file_path.lower().endswith(('.stl', '.obj')):
            self.show_geometry(file_path)
            return

        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except Exception as e:
            try:
                with open(file_path, 'r', encoding='latin1', errors='replace') as f:
                    text = f.read()
            except Exception:
                QMessageBox.critical(self, "Erro", f"Não foi possível abrir o arquivo:\n{e}")
                return
        self.open_file_in_tab(file_path, text)

    def lint_current(self):
        return

    def update_status(self):
        return
    def current_editor(self):
        w = self.editor_tabs.currentWidget()
        if w and hasattr(w, 'editor'):
            return w.editor
        return None

    def open_file_in_tab(self, file_path, text):
        if file_path in self.path_to_editor:
            editor = self.path_to_editor[file_path]
            container = editor.parentWidget()
            idx = self.editor_tabs.indexOf(container)
            if idx != -1:
                self.editor_tabs.setCurrentIndex(idx)
                return
        container = EditorContainerWidget(file_path=file_path)
        editor = container.editor
        editor.setPlainText(text)
        editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        editor.textChanged.connect(self.on_editor_text_changed)
        SimpleHighlighter(editor.document())
        f = QFont("Fira Code", 10)
        f.setStyleHint(QFont.Monospace)
        f.setFixedPitch(True)
        new_point = max(6, int(10 * self.scale))
        f.setPointSize(new_point)
        editor.setFont(f)
        if hasattr(editor, 'document'):
            editor.document().setDefaultFont(f)

        self.editor_stack.setCurrentWidget(self.editor_tabs)
        tab_label = os.path.basename(file_path)
        idx = self.editor_tabs.addTab(container, tab_label)
        self.editor_tabs.setCurrentIndex(idx)
        self.editor_tabs.setTabToolTip(idx, file_path)

        # Garante que a aba de Geometria continue sem botão de fechar
        for i in range(self.editor_tabs.count()):
            if self.editor_tabs.tabText(i) == "Geometry":
                self.editor_tabs.tabBar().setTabButton(i, QTabBar.RightSide, None)
                self.editor_tabs.tabBar().setTabButton(i, QTabBar.LeftSide, None)

        self.path_to_editor[file_path] = editor
        self.editor_to_path[editor] = file_path
        self.current_file = file_path
        self._update_simulation_layout()

    def show_geometry(self, file_path=None):
        """Abre o painel permanente de Geometria na primeira posição."""
        self.editor_stack.setCurrentWidget(self.editor_tabs)
        index_geom = self.editor_tabs.indexOf(self.geom_view)
        if index_geom == -1:
            index_geom = self.editor_tabs.insertTab(0, self.geom_view, "Geometry")
            self.editor_tabs.setTabToolTip(index_geom, "Case mesh visualization")

        # Remove o botão de fechar para a aba permanente
        for i in range(self.editor_tabs.count()):
            if self.editor_tabs.tabText(i) == "Geometry":
                self.editor_tabs.tabBar().setTabButton(i, QTabBar.RightSide, None)
                self.editor_tabs.tabBar().setTabButton(i, QTabBar.LeftSide, None)

        if self.current_case and self.geom_scanned_case != self.current_case:
            self.geom_view.scan_case(self.current_case)
            self.geom_scanned_case = self.current_case

        if file_path and not self.geom_view.select_mesh(file_path):
            self.geom_view.viewer.load_meshes([(os.path.basename(file_path), file_path)])

        self.editor_tabs.setCurrentIndex(index_geom)
        self._update_simulation_layout()

    def on_tab_close_requested(self, index):
        widget = self.editor_tabs.widget(index)
        if widget is None:
            return
        if widget == self.geom_view:
            # A aba de Geometria é permanente e não pode ser fechada
            return
        editor = widget.editor if hasattr(widget, 'editor') else widget
        path = self.editor_to_path.get(editor)
        if path:
            del self.path_to_editor[path]
        if editor in self.editor_to_path:
            del self.editor_to_path[editor]
        self.editor_tabs.removeTab(index)
        widget.deleteLater()
        if self.editor_tabs.count() == 0 and not self.current_case:
            self.editor_stack.setCurrentWidget(self.welcome_widget)
        self._update_simulation_layout()

    def save_file(self):
        editor = self.current_editor()
        if editor is None:
            return False
        path = self.editor_to_path.get(editor)
        if path is None:
            return False
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(editor.toPlainText())
            return True
        except Exception:
            return False

    def save_file_as(self, path):
        editor = self.current_editor()
        if editor is None:
            return False
        self.editor_to_path[editor] = path
        self.path_to_editor[path] = editor
        idx = self.editor_tabs.currentIndex()
        self.editor_tabs.setTabText(idx, os.path.basename(path))
        self.editor_tabs.setTabToolTip(idx, path)
        return self.save_file()

    def on_editor_text_changed(self):
        self.lint_current()

    def apply_scale(self):
        app = QApplication.instance()
        new_point = max(6, int(10 * self.scale))
        new_font = QFont("Inter", new_point)
        new_font.setStyleHint(QFont.SansSerif)
        app.setFont(new_font)

        for editor in list(self.editor_to_path.keys()):
            try:
                f = QFont("Fira Code", new_point)
                f.setStyleHint(QFont.Monospace)
                f.setFixedPitch(True)
                editor.setFont(f)
                if hasattr(editor, 'document'):
                    editor.document().setDefaultFont(f)
            except Exception:
                pass

        fv_font = self.file_view.font()
        fv_font.setPointSize(new_point)
        self.file_view.setFont(fv_font)

        self.file_view.setIconSize(QSize(int(20 * self.scale), int(20 * self.scale)))


    def apply_light_theme(self):
        app = QApplication.instance()
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#f4f4f4"))
        palette.setColor(QPalette.WindowText, QColor("#161616"))
        palette.setColor(QPalette.Base, QColor("#ffffff"))
        palette.setColor(QPalette.AlternateBase, QColor("#f4f4f4"))
        palette.setColor(QPalette.ToolTipBase, QColor("#393939"))
        palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
        palette.setColor(QPalette.Text, QColor("#161616"))
        palette.setColor(QPalette.Button, QColor("#e0e0e0"))
        palette.setColor(QPalette.ButtonText, QColor("#161616"))
        palette.setColor(QPalette.BrightText, QColor("#da1e28"))
        palette.setColor(QPalette.Highlight, QColor("#0f62fe"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        app.setPalette(palette)

        close_icon = icon_path('close_tab.svg').replace('\\', '/')
        close_hover_icon = icon_path('close_tab_hover.svg').replace('\\', '/')

        qss = """
            /* ── IBM Carbon Design System · g10 Theme ── */

            QMainWindow {
                background-color: #f4f4f4;
            }
            QWidget {
                background-color: #f4f4f4;
                color: #161616;
                font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
            }


            /* ── UI Shell Header (dark) ── */
            QToolBar {
                background-color: #161616;
                border: none;
                spacing: 0px;
                padding: 0px;
                min-height: 48px;
                max-height: 48px;
            }
            QToolBar QLabel {
                background: transparent;
                color: #ffffff;
                padding: 0px 14px 0px 12px;
                min-height: 48px;
                max-height: 48px;
            }
            QToolBar QToolButton, QToolBar QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 0px;
                padding: 0px 16px;
                margin: 0px;
                color: #ffffff;
                font-weight: 400;
                font-size: 13px;
                min-height: 48px;
                max-height: 48px;
            }
            QToolBar QToolButton:hover, QToolBar QPushButton:hover {
                background-color: #353535;
                color: #ffffff;
            }
            QToolBar QToolButton:pressed, QToolBar QPushButton:pressed {
                background-color: #525252;
                color: #ffffff;
            }
            QToolBar QToolButton:disabled, QToolBar QPushButton:disabled {
                color: #6f6f6f;
                background-color: transparent;
            }
            QToolBar::separator {
                width: 0px;
                background-color: transparent;
                margin: 0px;
            }



            /* ── Menus (dropdown) ── */
            QMenu {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 0;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 24px 6px 10px;
                color: #161616;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #e0e0e0;
                color: #161616;
            }
            QMenu::separator {
                height: 1px;
                background: #e0e0e0;
                margin: 4px 0;
            }

            /* ── Buttons ── */
            QPushButton {
                background-color: #0f62fe;
                color: #ffffff;
                border: none;
                border-radius: 0;
                padding: 11px 16px;
                font-weight: 400;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0353e9;
            }
            QPushButton:pressed {
                background-color: #002d9c;
            }
            QPushButton:disabled {
                background-color: #c6c6c6;
                color: #8d8d8d;
            }

            /* ── Inputs ── */
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
                background-color: #ffffff;
                color: #161616;
                border: none;
                border-bottom: 1px solid #8d8d8d;
                border-radius: 0;
                padding: 8px 16px;
                font-size: 14px;
                selection-background-color: #0f62fe;
                selection-color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
                border-bottom: 2px solid #0f62fe;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }

            /* ── Text Areas & Code Editor (Fira Code) ── */
            QPlainTextEdit, QTextEdit, QPlainTextEdit#CodeEditor {
                background-color: #ffffff;
                color: #161616;
                border: 1px solid #e0e0e0;
                border-radius: 0;
                font-family: "Fira Code", "IBM Plex Mono", "Consolas", "Courier New", monospace;
                selection-background-color: #0f62fe;
                selection-color: #ffffff;
            }
            QTextEdit:focus, QPlainTextEdit:focus {
                border: 1px solid #e0e0e0;
            }

            /* ── Tabs (underline style) ── */
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 0;
                background: #ffffff;
            }
            QTabBar::tab {
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 6px 10px;
                color: #525252;
                font-weight: 400;
                font-size: 12px;
                margin: 0;
            }
            QTabBar::tab:selected {
                color: #161616;
                border-bottom: 2px solid #0f62fe;
                font-weight: 400;
            }
            QTabBar::tab:hover:!selected {
                color: #161616;
                border-bottom: 2px solid #8d8d8d;
            }
            QTabBar::close-button {
                image: url(CLOSE_ICON_URL);
                subcontrol-position: right;
                margin-left: 6px;
                margin-right: 2px;
                padding: 1px;
                width: 14px;
                height: 14px;
            }
            QTabBar::close-button:hover {
                image: url(CLOSE_HOVER_ICON_URL);
            }

            /* ── Tree View (file browser) ── */
            QTreeView {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 0;
                padding: 0;
            }
            QTreeView::item {
                padding: 6px 4px;
                border: none;
            }
            QTreeView::item:hover {
                background-color: #e8e8e8;
            }
            QTreeView::item:selected {
                background-color: #e0e0e0;
                color: #161616;
            }
            QTreeView QHeaderView::section {
                background-color: #e0e0e0;
                border: none;
                border-bottom: 1px solid #c6c6c6;
                padding: 8px;
                font-weight: 600;
                color: #161616;
            }

            /* ── List View / List Widget ── */
            QListView, QListWidget {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 0;
            }
            QListView::item:hover, QListWidget::item:hover {
                background-color: #e8e8e8;
            }
            QListView::item:selected, QListWidget::item:selected {
                background-color: #e0e0e0;
                color: #161616;
            }

            /* ── Status Bar ── */
            QStatusBar {
                border-top: 1px solid #e0e0e0;
                background: #ffffff;
                padding: 4px 16px;
                color: #525252;
                font-size: 12px;
            }

            /* ── Progress Bar ── */
            QProgressBar {
                border: none;
                background: #e0e0e0;
                border-radius: 0;
                text-align: center;
                font-weight: 600;
                font-size: 12px;
                color: #161616;
            }
            QProgressBar::chunk {
                background-color: #0f62fe;
                border-radius: 0;
            }

            /* ── Splitters ── */
            QSplitter::handle {
                background: #e0e0e0;
            }
            QSplitter::handle:horizontal {
                width: 1px;
            }
            QSplitter::handle:vertical {
                height: 1px;
            }

            /* ── Dock Widget ── */
            QDockWidget {
                font-size: 14px;
                titlebar-close-icon: none;
            }
            QDockWidget::title {
                background-color: #e0e0e0;
                padding: 8px 16px;
                font-weight: 600;
                color: #161616;
                border: none;
            }

            /* ── Scroll Bars ── */
            QScrollBar:vertical {
                background: #f4f4f4;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #c6c6c6;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8d8d8d;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar:horizontal {
                background: #f4f4f4;
                height: 8px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #c6c6c6;
                min-width: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #8d8d8d;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
            }

            /* ── Tooltips ── */
            QToolTip {
                background-color: #393939;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                font-size: 12px;
            }

            /* ── Form Labels ── */
            QFormLayout QLabel {
                color: #525252;
                font-size: 12px;
            }
            """
        app.setStyleSheet(
            qss.replace("CLOSE_ICON_URL", close_icon).replace("CLOSE_HOVER_ICON_URL", close_hover_icon)
        )

    def wheelEvent(self, event):
        super().wheelEvent(event)

    def zoom_in(self):
        self.scale *= 1.15
        self.apply_scale()

    def zoom_out(self):
        self.scale = max(0.5, self.scale / 1.15)
        self.apply_scale()

    def zoom_reset(self):
        self.scale = 1.6
        self.apply_scale()



    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.log(data)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.log(f"[ERR] {data}")

    def process_finished(self):
        self.log("\nProcesso finalizado.\n")

    def _update_simulation_layout(self):
        """Ajusta dinamicamente a largura do gráfico e do editor de texto."""
        if not hasattr(self, 'residuals_view') or not hasattr(self, 'top_splitter'):
            return
        if self.residuals_view.isVisible():
            if self.editor_tabs.count() == 0:
                self.editor_stack.hide()
                self.residuals_view.show()
                self.top_splitter.setSizes([0, 1000])
            else:
                self.editor_stack.show()
                self.residuals_view.show()
                total_w = max(400, self.top_splitter.width())
                self.top_splitter.setSizes([int(total_w * 0.5), int(total_w * 0.5)])
        else:
            self.editor_stack.show()
            self.residuals_view.hide()
            self.top_splitter.setSizes([1000, 0])

    def parse_residuals(self, text):
        """Extrai grandezas do log e as encaminha ao gráfico, monitor e status bar."""
        # Verificação de divergência no texto cru
        text_alerts = logparse.detect_divergence_in_text(text)
        if text_alerts:
            if hasattr(self, 'divergence_banner'):
                self.divergence_banner.setText(f"⚠ Alert: {text_alerts[0].message}")
                self.divergence_banner.setVisible(True)
            self.log(f"\n[DIVERGENCE ALERT] {text_alerts[0].message}\n")

        steps = logparse.parse_all_time_steps(text)
        if not steps:
            values, sim_time = logparse.parse_residuals(text)
            if values:
                steps = [(values, sim_time)]
            elif sim_time is not None:
                self.current_sim_time = sim_time
                if hasattr(self, 'kpi_time'):
                    self.kpi_time.setText(f"t: {sim_time:.4f}s")
                return

        for values, sim_time in steps:
            if sim_time is not None:
                self.current_sim_time = sim_time
                if hasattr(self, 'kpi_time'):
                    self.kpi_time.setText(f"t: {sim_time:.4f}s")
            if values:
                # Verificação de divergência nos valores numéricos (NaN, spike, Courant)
                prev = getattr(self, '_previous_residuals', None)
                alerts = logparse.detect_divergence(values, prev)
                if alerts:
                    if hasattr(self, 'divergence_banner'):
                        self.divergence_banner.setText(f"⚠ Divergence Warning: {alerts[0].message}")
                        self.divergence_banner.setVisible(True)
                    self.log(f"[DIVERGENCE WARNING] {alerts[0].message}\n")

                self._previous_residuals = dict(values)

                if hasattr(self, 'kpi_co'):
                    co_val = values.get("Co max", values.get("Co mean"))
                    if co_val is not None:
                        self.kpi_co.setText(f"Co max: {co_val:.3g}")
                if hasattr(self, 'sim_iter_count'):
                    self.sim_iter_count += 1
                    if hasattr(self, 'kpi_iter'):
                        self.kpi_iter.setText(f"Iter: #{self.sim_iter_count}")
                self.residuals_view.update_residuals(values, getattr(self, 'current_sim_time', None))
                for name, val in values.items():
                    self.convergence_monitor.update_residual(name, val)


    def _get_process_targets(self):
        """Coleta PIDs de todos os processos filhos da simulação/caso."""
        targets = set()
        if self.process.state() != QProcess.NotRunning:
            root_pid = int(self.process.processId())
            targets.add(root_pid)

            def _children_of(pid):
                try:
                    out = subprocess.check_output(
                        ['ps', '-o', 'pid=', '--ppid', str(pid)], text=True
                    )
                    return [int(x) for x in out.split() if x.strip().isdigit()]
                except Exception:
                    return []

            def _descendants(pid):
                stack = [pid]
                found = set()
                while stack:
                    cur = stack.pop()
                    for ch in _children_of(cur):
                        if ch not in found:
                            found.add(ch)
                            stack.append(ch)
                return found

            targets.update(_descendants(root_pid))

        if self.current_case:
            targets.update(self._find_case_related_processes(self.current_case))

        targets.discard(os.getpid())
        return targets

    def toggle_pause_simulation(self):
        """Pausa ou retoma a execução enviando SIGSTOP ou SIGCONT aos processos."""
        targets = self._get_process_targets()
        if not targets and self.process.state() == QProcess.NotRunning and not self.detached_run_active:
            return

        if not self.is_paused:
            for pid in sorted(targets):
                try:
                    os.kill(pid, signal.SIGSTOP)
                except Exception:
                    pass
            self.is_paused = True
            self.pause_action.setText("Resume")
            self.status_label.setText("Paused")
            self.log("[SIM] Simulation paused.\n")
        else:
            for pid in sorted(targets):
                try:
                    os.kill(pid, signal.SIGCONT)
                except Exception:
                    pass
            self.is_paused = False
            self.pause_action.setText("Pause")
            self.status_label.setText("Running")
            self.log("[SIM] Simulation resumed.\n")

    def _run_command_in_case(self, command, args=None, follow_solver_log=False):
        if not getattr(self, 'current_case', None):
            QMessageBox.warning(self, "Warning", "No case opened. Please select a case before running this command.")
            return
        if args is None:
            args = []
        if self.detached_run_active and self.current_case:
            alive = self._find_case_related_processes(self.current_case)
            alive.discard(os.getpid())
            if alive:
                self.log(
                    "Case processes are still running in the background. "
                    "Use Stop before starting a new command.\n"
                )
                return
        self.follow_solver_log = bool(follow_solver_log)
        if not self.follow_solver_log:
            self.log_follow_path = None
            self.log_follow_pos = 0
            self.log_follow_ino = None
            self.log_follow_shown_path = None
            self.log_follow_timer.stop()
        if self.process.state() != QProcess.NotRunning:
            self.log("Another process is currently running. Please wait for completion.\n")
            return
        self.process.setWorkingDirectory(self.current_case)
        self.log(f"$ {command} {' '.join(args)}\n")
        
        if follow_solver_log:
            self.residuals_view.setVisible(True)
            self.show_tab("Simulation")
        else:
            self.residuals_view.setVisible(False)
            self.show_tab("Console")
        self._update_simulation_layout()
            
        try:
            self.process.start(command, args)
        except Exception as e:
            self.log(f"Failed to start {command}: {e}\n")

    def stop_process(self):
        running = self.process.state() != QProcess.NotRunning
        detached = self.detached_run_active
        if not running and not detached:
            return
        try:
            self.log("Requesting process termination...\n")
            targets = self._get_process_targets()

            for pid in sorted(targets, reverse=True):
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except Exception:
                    pass

            if running and not self.process.waitForFinished(2500):
                self.log("Force killing process and child processes...\n")
                for pid in sorted(targets, reverse=True):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except Exception:
                        pass
                self.process.kill()

            self.log_follow_timer.stop()
            self.detached_run_active = False
            self.follow_solver_log = False
            self._set_idle_ui()
        except Exception as e:
            self.log(f"Error stopping process: {e}\n")

    def _on_process_started(self):
        try:
            self.status_label.setText("Running")
            self.status_progress.setVisible(True)
            self.run_action.setEnabled(False)
            self.pause_action.setEnabled(True)
            self.pause_action.setText("Pause")
            self.stop_action.setEnabled(True)
            self.is_paused = False
            self.sim_iter_count = 0
            if self.follow_solver_log:
                self.log_follow_timer.start()
        except Exception:
            pass

    def _on_process_finished(self, exitCode, exitStatus):
        try:
            if self.follow_solver_log:
                self._poll_solver_log()
                self.detached_run_active = True
                self.detached_last_log_growth = time.time()
                if self.log_follow_path and os.path.isfile(self.log_follow_path):
                    try:
                        self.log_follow_last_size = os.path.getsize(self.log_follow_path)
                    except Exception:
                        self.log_follow_last_size = 0
                self.status_label.setText("Running (bg)")
                self.status_progress.setVisible(True)
                self.run_action.setEnabled(False)
                self.pause_action.setEnabled(True)
                self.stop_action.setEnabled(True)
                self.log_follow_timer.start()
                return
            self.log_follow_timer.stop()
            self._set_idle_ui()
        except Exception:
            pass

    def _set_idle_ui(self):
        self.status_label.setText("Idle")
        self.status_progress.setVisible(False)
        self.run_action.setEnabled(True)
        self.pause_action.setEnabled(False)
        self.pause_action.setText("Pause")
        self.stop_action.setEnabled(False)
        self.is_paused = False
        try:
            QApplication.beep()
        except Exception:
            pass

    def run_blockMesh(self):
        self._run_command_in_case('blockMesh')

    def run_checkMesh(self):
        self._run_command_in_case('checkMesh')

    def run_snappyHexMesh(self):
        case = getattr(self, 'current_case', None)
        if not case:
            QMessageBox.warning(self, "Warning", "No case opened. Please select a case before generating mesh.")
            return

        mesh_sh_path = os.path.join(case, 'mesh.sh')
        if not os.path.exists(mesh_sh_path):
            try:
                content = (
                    "#!/usr/bin/env bash\n"
                    "set -e\n"
                    "cd \"${0%/*}\" || exit 1\n\n"
                    ". $WM_PROJECT_DIR/bin/tools/RunFunctions 2>/dev/null || true\n\n"
                    "echo \"==> 1. Cleaning previous times and meshes...\"\n"
                    "rm -rf 0.* [1-9]* processor* constant/polyMesh log.*\n\n"
                    "echo \"==> 2. Generating base mesh (blockMesh)...\"\n"
                    "blockMesh\n\n"
                    "if [ -f \"system/surfaceFeaturesDict\" ]; then\n"
                    "    echo \"==> 3. Extracting surface features (surfaceFeatures)...\"\n"
                    "    surfaceFeatures\n"
                    "fi\n\n"
                    "echo \"==> 4. Running snappyHexMesh (-overwrite)...\"\n"
                    "snappyHexMesh -overwrite\n\n"
                    "echo \"==> 5. Checking mesh quality (checkMesh)...\"\n"
                    "checkMesh -constant\n\n"
                    "echo \"==> Mesh process completed successfully!\"\n"
                )
                with open(mesh_sh_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log("Standard mesh.sh created automatically.\n")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create mesh.sh: {e}")
                return

        try:
            st = os.stat(mesh_sh_path)
            if not (st.st_mode & stat.S_IXUSR):
                os.chmod(mesh_sh_path, st.st_mode | stat.S_IXUSR)
        except Exception as e:
            self.log(f"Warning: could not make mesh.sh executable: {e}\n")

        self._run_command_in_case('/bin/bash', ['-lc', './mesh.sh'])

    def run_decomposePar(self):
        self._run_command_in_case('decomposePar')

    def run_reconstructPar(self):
        self._run_command_in_case('reconstructPar')

    def run_yPlus(self):
        self._run_command_in_case('yPlus')

    def run_allclean(self):
        if self.current_case:
            cmd = "./Allclean" if os.path.exists(os.path.join(self.current_case, "Allclean")) else "foamCleanTutorials"
            self._run_command_in_case(cmd)

    def verify_current_case(self):
        """Executa verificação global do caso e exibe relatório no Console e em diálogo."""
        case = getattr(self, 'current_case', None)
        if not case:
            QMessageBox.warning(self, "Warning", "No case opened. Please select a case before verifying.")
            return

        is_valid, issues, warnings = foamdict.verify_case(case)
        
        report_lines = ["\n" + "="*50, " [PRE-FLIGHT CASE VERIFICATION REPORT]", "="*50]
        if is_valid:
            report_lines.append("✓ Case structure and essential files are VALID.")
        else:
            report_lines.append("✗ CRITICAL ISSUES FOUND:")
            for issue in issues:
                report_lines.append(f"  • {issue}")

        if warnings:
            report_lines.append("\n⚠ WARNINGS / SUGGESTIONS:")
            for warn in warnings:
                report_lines.append(f"  • {warn}")
        report_lines.append("="*50 + "\n")

        self.log("\n".join(report_lines))

        if not is_valid:
            msg = "Pre-flight verification found critical issues:\n\n• " + "\n• ".join(issues)
            if warnings:
                msg += "\n\nWarnings:\n• " + "\n• ".join(warnings)
            QMessageBox.critical(self, "Pre-flight Check: Issues Found", msg)
        elif warnings:
            msg = "Case is valid with the following warnings:\n\n• " + "\n• ".join(warnings)
            QMessageBox.warning(self, "Pre-flight Check: Ready with Warnings", msg)
        else:
            QMessageBox.information(
                self,
                "Pre-flight Check: Passed",
                "✓ All case checks passed!\n\n• Directories (0, constant, system): OK\n• Mesh (constant/polyMesh): OK\n• Dictionaries (controlDict, fvSchemes, fvSolution): OK"
            )

    def run_simulation(self):
        """Executa `./Allrun` dentro do diretório do caso, se existir."""
        case = getattr(self, 'current_case', None)
        if not case:
            QMessageBox.warning(self, "Warning", "No case opened. Please select a case before running simulation.")
            return

        # Reseta alertas de divergência e histórico prévio
        if hasattr(self, 'divergence_banner'):
            self.divergence_banner.setVisible(False)
        self._previous_residuals = {}

        # Verificação global antes de iniciar a simulação (Pre-flight check)
        is_valid, issues, warnings = foamdict.verify_case(case)

        if not is_valid:
            issues_str = "\n• " + "\n• ".join(issues)
            self.log(f"\n[PRE-FLIGHT CHECK FAILED] Cannot start simulation:\n{issues_str}\n")
            
            # Se o único problema for malha ausente, sugere gerar a malha
            if any("constant/polyMesh" in err for err in issues):
                resp = QMessageBox.question(
                    self,
                    "Pre-flight Check: Mesh Missing",
                    f"Simulation cannot start because mesh was not found:\n{issues_str}\n\nWould you like to run mesh generation (mesh.sh) now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if resp == QMessageBox.Yes:
                    self.run_snappyHexMesh()
                return

            QMessageBox.critical(
                self,
                "Pre-flight Check Failed",
                f"Cannot start simulation due to the following issues:\n{issues_str}"
            )
            return

        if warnings:
            warn_str = "\n• " + "\n• ".join(warnings)
            self.log(f"[PRE-FLIGHT CHECK] Warnings:\n{warn_str}\n")

        allrun_path = os.path.join(case, 'Allrun')
        if not os.path.exists(allrun_path):
            try:
                content = (
                    "#!/bin/bash\n"
                    "set -e\n"
                    "cd \"${0%/*}\" || exit 1\n\n"
                    ". $WM_PROJECT_DIR/bin/tools/RunFunctions\n\n"
                    "if [ ! -d \"constant/polyMesh\" ]; then\n"
                    "    echo \"==> Error: constant/polyMesh not found! Run mesh.sh or blockMesh first.\" >&2\n"
                    "    exit 1\n"
                    "fi\n\n"
                    "rm -rf processor* log.*\n\n"
                    "if [ -f \"system/decomposeParDict\" ]; then\n"
                    "    echo \"==> Decomposing case (decomposePar)...\"\n"
                    "    decomposePar\n"
                    "    echo \"==> Running parallel solver...\"\n"
                    "    runParallel $(getApplication)\n"
                    "else\n"
                    "    echo \"==> Running serial solver...\"\n"
                    "    $(getApplication)\n"
                    "fi\n"
                )
                with open(allrun_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log("Standard Allrun created automatically.\n")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create Allrun: {e}")
                return

        try:
            st = os.stat(allrun_path)
            if not (st.st_mode & stat.S_IXUSR):
                os.chmod(allrun_path, st.st_mode | stat.S_IXUSR)
        except Exception as e:
            self.log(f"Warning: could not make Allrun executable: {e}\n")

        self.log_follow_path = None
        self.log_follow_pos = 0
        self.log_follow_ino = None
        self.log_follow_shown_path = None
        self.current_sim_time = 0.0
        self.sim_log_view.clear()
        self._run_command_in_case('/bin/bash', ['-lc', f'./Allrun'], follow_solver_log=True)

    def _handle_process_finished_log(self):
        if self.follow_solver_log:
            self.log("\nAllrun finished; monitoring solver in background...\n")
        else:
            self.log("\nProcess finished.\n")

    def _choose_solver_log_file(self):
        """Log do solver do caso atual, ou None se não houver."""
        return logparse.choose_solver_log_file(getattr(self, 'current_case', None))

    def _poll_solver_log(self):
        if not self.follow_solver_log:
            return

        if not self.log_follow_path or not os.path.isfile(self.log_follow_path):
            self.log_follow_path = self._choose_solver_log_file()
            self.log_follow_pos = 0
            self.log_follow_ino = None
            if self.log_follow_path:
                self.log(f"Monitoring residuals in: {self.log_follow_path}\n")
                self.log_follow_shown_path = self.log_follow_path
                self._append_sim_log(f"[tail -f] {self.log_follow_path}\n")

        if not self.log_follow_path or not os.path.isfile(self.log_follow_path):
            return

        try:
            st = os.stat(self.log_follow_path)
            if self.log_follow_ino is None:
                self.log_follow_ino = st.st_ino
            elif self.log_follow_ino != st.st_ino or st.st_size < self.log_follow_pos:
                self.log_follow_pos = 0
                self.log_follow_ino = st.st_ino

            with open(self.log_follow_path, 'r', encoding='utf-8', errors='replace') as fh:
                fh.seek(self.log_follow_pos)
                chunk = fh.read()
                self.log_follow_pos = fh.tell()

            if chunk:
                self._append_sim_log(chunk)
                self.parse_residuals(chunk)
                self.detached_last_log_growth = time.time()

            if self.detached_run_active:
                alive = self._find_case_related_processes(self.current_case or "")
                alive.discard(os.getpid())
                if alive:
                    self.status_label.setText("Running (bg)")
                    self.status_progress.setVisible(True)
                    self.run_action.setEnabled(False)
                    self.stop_action.setEnabled(True)
                    return

                try:
                    cur_size = os.path.getsize(self.log_follow_path)
                except Exception:
                    cur_size = self.log_follow_last_size
                if cur_size != self.log_follow_last_size:
                    self.log_follow_last_size = cur_size
                    self.detached_last_log_growth = time.time()

                if (time.time() - self.detached_last_log_growth) >= self.detached_stale_seconds:
                    self.detached_run_active = False
                    self.follow_solver_log = False
                    self.log_follow_timer.stop()
                    self._set_idle_ui()
                    self.log("\nProcesso finalizado (log estabilizado).\n")
        except Exception:
            pass

    def _append_sim_log(self, text):
        if not text:
            return
        try:
            self.sim_log_view.moveCursor(QTextCursor.End)
            self.sim_log_view.insertPlainText(text)
            # Garante que a barra de rolagem fique sempre no final (mostrando as iterações mais recentes)
            sb = self.sim_log_view.verticalScrollBar()
            sb.setValue(sb.maximum())
            self.sim_log_view.moveCursor(QTextCursor.End)
        except Exception:
            pass

    def _find_case_related_processes(self, case_path):
        targets = set()
        try:
            out = subprocess.check_output(['ps', '-eo', 'pid=,args='], text=True)
        except Exception:
            return targets

        keywords = (
            'foamRun', 'Foam', 'simpleFoam', 'pimpleFoam', 'pisoFoam',
            'interFoam', 'rhoPimpleFoam', 'mpirun', 'mpiexec', 'decomposePar',
            'reconstructPar'
        )

        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            pid_txt, cmd = parts
            if case_path not in cmd:
                continue
            if not any(k in cmd for k in keywords):
                continue
            try:
                targets.add(int(pid_txt))
            except ValueError:
                pass
        return targets

    def open_paraview(self):
        """Lança o ParaView desvinculado com o arquivo de caso .foam."""
        case = getattr(self, 'current_case', None)
        if not case:
            QMessageBox.warning(self, "Warning", "No case opened. Please select a case before opening ParaView.")
            return

        case_name = os.path.basename(os.path.normpath(case))
        foam_file = os.path.join(case, f"{case_name}.foam")
        if not os.path.exists(foam_file):
            try:
                with open(foam_file, 'w', encoding='utf-8') as f:
                    pass
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create .foam anchor file: {e}")
                return

        pv_bin = shutil.which("paraview")
        if not pv_bin:
            pv_bin = shutil.which("paraFoam")

        if not pv_bin:
            QMessageBox.warning(
                self,
                "ParaView Not Found",
                "ParaView executable ('paraview' or 'paraFoam') was not found in system PATH.\n\n"
                "Please install ParaView from https://www.paraview.org/download/ and ensure it is available in your PATH.\n\n"
                f"Anchor file created: {foam_file}"
            )
            return

        try:
            # Lança o ParaView em processo separado e desvinculado
            subprocess.Popen([pv_bin, foam_file], start_new_session=True)
            self.log(f"ParaView launched for: {foam_file}\n")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch ParaView: {e}")

    def export_report(self):
        """Gera relatório técnico da simulação em PDF."""
        case = getattr(self, 'current_case', None)
        if not case:
            QMessageBox.warning(self, "Warning", "No case opened. Please select a case before exporting report.")
            return

        pdf_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Simulation Report",
            os.path.join(case, "simulation_report.pdf"),
            "PDF Files (*.pdf)"
        )
        if not pdf_path:
            return

        if not pdf_path.lower().endswith(".pdf"):
            pdf_path += ".pdf"

        pixmap = None
        if hasattr(self, 'residuals_view') and self.residuals_view.isVisible():
            try:
                pixmap = self.residuals_view.grab()
            except Exception:
                pixmap = None

        convergence_data = {}
        if hasattr(self, 'residuals_view') and hasattr(self.residuals_view, 'history'):
            for var, hist in self.residuals_view.history.items():
                if hist:
                    convergence_data[var] = hist[-1]

        ctrl = foamdict.read_control_dict(case)
        sim_info = {
            "solver": ctrl.get("application", "N/A"),
            "endTime": ctrl.get("endTime", "N/A"),
            "deltaT": ctrl.get("deltaT", "N/A"),
            "iterations": str(getattr(self, 'sim_iter_count', 0)),
            "sim_time": f"{getattr(self, 'current_sim_time', 0.0):.4f} s",
        }

        gen = ReportGenerator(
            case_path=case,
            chart_pixmap=pixmap,
            convergence_data=convergence_data,
            sim_info=sim_info,
        )

        if gen.generate_pdf(pdf_path):
            self.log(f"Simulation report exported: {pdf_path}\n")
            QMessageBox.information(
                self,
                "Report Exported",
                f"Simulation report successfully exported to:\n{pdf_path}"
            )
        else:
            QMessageBox.critical(self, "Error", "Failed to generate PDF report.")
