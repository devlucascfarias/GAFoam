import sys
import os
import signal
import subprocess
import glob
import time
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QTextEdit, QPlainTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QMenuBar, QMenu, QSplitter, QTabWidget, QFileDialog, QMessageBox, QToolBar, QLabel, QProgressBar, QDockWidget, QFormLayout, QDoubleSpinBox, QHeaderView, QTableWidget, QTableWidgetItem, QToolButton
from PySide6.QtGui import QAction, QIcon, QFont, QKeySequence, QPalette, QColor, QTextCharFormat, QPainter, QTextCursor
from PySide6.QtCore import QProcess, Qt, QSize, QRegularExpression, QRect, QTimer
from editor import CodeEditor, SimpleHighlighter, EditorContainerWidget
from filebrowser import FileBrowser
from stl_viewer import STLViewer, CaseGeometryWidget
from residuals import ResidualsWidget
from menus import setup_menus
from handlers import make_stdout_handler, make_stderr_handler, make_finished_handler
from terminal import TerminalWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interface OpenFOAM")
        self.resize(1024, 768)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self.on_tab_close_requested)

        self.geom_view = CaseGeometryWidget(parent=self)
        self.editor_tabs.addTab(self.geom_view, "Geometria")

        self.path_to_editor = {}
        self.editor_to_path = {}
        self.current_case = None

        self.tab_widget = QTabWidget()
        
        # 1. Console de Execução (logs da interface e saída padrão de comandos)
        self.console_view = QTextEdit(parent=self)
        self.console_view.setReadOnly(True)
        self.console_view.setStyleSheet(
            "font-family: 'Consolas', 'Monaco', 'Courier New', monospace; "
            "font-size: 10pt; line-height: 1.4; border: none; padding: 6px;"
        )
        self.tab_widget.addTab(self.console_view, "Console")

        # 2. Simulação (Visualização do Solver com Monitor de Convergência acoplado)
        sim_container = QWidget(parent=self)
        sim_layout = QHBoxLayout(sim_container)
        sim_layout.setContentsMargins(0, 0, 0, 0)
        sim_layout.setSpacing(0)

        self.sim_log_view = QTextEdit(parent=self)
        self.sim_log_view.setReadOnly(True)
        self.sim_log_view.setStyleSheet(
            "font-family: 'Consolas', 'Monaco', 'Courier New', monospace; "
            "font-size: 10pt; line-height: 1.4; border: none; padding: 6px;"
        )
        sim_layout.addWidget(self.sim_log_view, 2)

        self.convergence_monitor = ConvergenceMonitorWidget(parent=self)
        self.convergence_monitor.setFixedWidth(280)
        self.convergence_monitor.setStyleSheet("background-color: #f8f9fa; border-left: 1px solid #dee2e6;")
        sim_layout.addWidget(self.convergence_monitor)

        self.tab_widget.addTab(sim_container, "Simulação")

        self.residuals_view = ResidualsWidget(parent=self)

        self.top_splitter = QSplitter(Qt.Horizontal)
        self.top_splitter.addWidget(self.editor_tabs)
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

        # 3. Dock Widget para controlDict (Parâmetros do Caso)
        self.control_dock = ControlDictDockWidget(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.control_dock)
        
        # Sincroniza o toggleViewAction com o menu "Exibir"
        toggle_dock_act = self.control_dock.toggleViewAction()
        toggle_dock_act.setText("Parâmetros do Caso (controlDict)")
        
        view_menu = None
        for action in self.menuBar().actions():
            if action.text() == "Exibir":
                view_menu = action.menu()
                break
        if not view_menu:
            view_menu = self.menuBar().addMenu("Exibir")
        view_menu.addAction(toggle_dock_act)

        try:
            self.toolbar = QToolBar("Run")
            self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.toolbar.setIconSize(QSize(18, 18))
            self.addToolBar(self.toolbar)

            case_icon = self._load_svg_icon('open_case.svg', 'folder-open')
            case_act = QAction(case_icon, 'Abrir Caso', self)
            case_act.setToolTip('Selecionar Caso')
            case_act.setStatusTip('Selecionar a pasta do caso OpenFOAM')
            case_act.triggered.connect(self.selecionar_caso)
            self.toolbar.addAction(case_act)
            self.toolbar.addSeparator()

            run_icon = self._load_svg_icon('run_allrun.svg', 'media-playback-start')
            stop_icon = self._load_svg_icon('stop_process.svg', 'media-playback-stop')

            self.run_action = QAction(run_icon, '', self)
            self.run_action.setToolTip('Rodar (Ctrl+R)')
            self.run_action.setStatusTip('Rodar simulação (Allrun)')
            self.run_action.setShortcut(QKeySequence('Ctrl+R'))
            self.run_action.triggered.connect(self.run_simulation)
            self.toolbar.addAction(self.run_action)

            self.stop_action = QAction(stop_icon, '', self)
            self.stop_action.setToolTip('Parar')
            self.stop_action.setStatusTip('Parar processo em execução')
            self.stop_action.triggered.connect(self.stop_process)
            self.stop_action.setEnabled(False)
            self.toolbar.addAction(self.stop_action)
        except Exception:
            pass

        try:
            self.toolbar.addSeparator()

            block_act = QAction('blockMesh', self)
            block_act.setStatusTip('Executar blockMesh')
            block_act.triggered.connect(self.run_blockMesh)
            self.toolbar.addAction(block_act)

            check_act = QAction('checkMesh', self)
            check_act.setStatusTip('Executar checkMesh')
            check_act.triggered.connect(self.run_checkMesh)
            self.toolbar.addAction(check_act)

            snappy_act = QAction('snappyHexMesh', self)
            snappy_act.setStatusTip('Executar snappyHexMesh')
            snappy_act.triggered.connect(self.run_snappyHexMesh)
            self.toolbar.addAction(snappy_act)

            self.toolbar.addSeparator()

            # Botão de dropdown para Utilitários extras
            self.util_btn = QToolButton(self)
            self.util_btn.setText("Utilitários")
            self.util_btn.setIcon(self._load_svg_icon('gear.svg', 'system-run'))
            self.util_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.util_btn.setPopupMode(QToolButton.InstantPopup)
            self.util_btn.setStyleSheet(
                "QToolButton { padding: 4px 8px; border: 1px solid #ced4da; border-radius: 4px; background-color: #ffffff; color: #212529; font-weight: bold; }"
                "QToolButton::menu-indicator { image: none; }"
                "QToolButton:hover { background-color: #e9ecef; }"
            )
            
            util_menu = QMenu(self)
            
            decomp_act = QAction("decomposePar (Decompor)", self)
            decomp_act.triggered.connect(self.run_decomposePar)
            util_menu.addAction(decomp_act)
            
            recon_act = QAction("reconstructPar (Reconstruir)", self)
            recon_act.triggered.connect(self.run_reconstructPar)
            util_menu.addAction(recon_act)
            
            yplus_act = QAction("yPlus (Inspecionar Parede)", self)
            yplus_act.triggered.connect(self.run_yPlus)
            util_menu.addAction(yplus_act)
            
            util_menu.addSeparator()
            
            clean_act = QAction("Limpar Caso (Allclean)", self)
            clean_act.triggered.connect(self.run_allclean)
            util_menu.addAction(clean_act)
            
            self.util_btn.setMenu(util_menu)
            self.toolbar.addWidget(self.util_btn)
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
        self.log_follow_timer = QTimer(self)
        self.log_follow_timer.setInterval(600)
        self.log_follow_timer.timeout.connect(self._poll_solver_log)

        try:
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
        icon_path = os.path.join(os.path.dirname(__file__), 'icons', filename)
        if os.path.isfile(icon_path):
            return QIcon(icon_path)
        if fallback_theme:
            return QIcon.fromTheme(fallback_theme)
        return QIcon()

    def selecionar_caso(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        import os
        dir_path = QFileDialog.getExistingDirectory(self, "Selecione a pasta do caso OpenFOAM")
        if not dir_path:
            return
        required_dirs = ["0", "constant", "system"]
        missing = [d for d in required_dirs if not os.path.isdir(os.path.join(dir_path, d))]
        if missing:
            QMessageBox.critical(self, "Erro", f"A pasta selecionada não contém as subpastas obrigatórias: {', '.join(missing)}")
            return
        self.log(f"Caso aberto: {dir_path}\n")
        self.show_tab("Console")
        self.file_browser.set_root(dir_path)
        self.current_case = dir_path
        self.geom_view.scan_case(dir_path)
        self.control_dock.load_case(dir_path)
        self.convergence_monitor.load_case(dir_path)

        QMessageBox.information(self, "Sucesso", f"Caso OpenFOAM aberto com sucesso!\n{dir_path}")
    def on_file_clicked(self, index):

        if not index.isValid():
            return
        if self.file_browser.file_model.isDir(index):
            return
        file_path = self.file_browser.file_model.filePath(index)
        
        if file_path.lower().endswith(".stl"):
            self.open_stl_in_tab(file_path)
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    text = f.read()
            except Exception as e:
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
        import os
        if file_path in self.path_to_editor:
            editor = self.path_to_editor[file_path]
            container = editor.parentWidget()
            idx = self.editor_tabs.indexOf(container)
            if idx != -1:
                self.editor_tabs.setCurrentIndex(idx)
                return
        container = EditorContainerWidget()
        editor = container.editor
        editor.setPlainText(text)
        editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        editor.textChanged.connect(self.on_editor_text_changed)
        SimpleHighlighter(editor.document())

        f = editor.font()
        base_point = f.pointSize()
        if base_point <= 0:
            base_point = 10
        new_point = max(6, int(base_point * self.scale))
        f.setPointSize(new_point)
        editor.setFont(f)

        tab_label = os.path.basename(file_path)
        idx = self.editor_tabs.addTab(container, tab_label)
        self.editor_tabs.setCurrentIndex(idx)
        self.editor_tabs.setTabToolTip(idx, file_path)

        self.path_to_editor[file_path] = editor
        self.editor_to_path[editor] = file_path
        self.current_file = file_path

    def open_stl_in_tab(self, file_path):
        import os
        if file_path in self.path_to_editor:
            viewer = self.path_to_editor[file_path]
            idx = self.editor_tabs.indexOf(viewer)
            if idx != -1:
                self.editor_tabs.setCurrentIndex(idx)
                return

        viewer = STLViewer()
        viewer.load_stl(file_path)

        tab_label = os.path.basename(file_path)
        idx = self.editor_tabs.addTab(viewer, tab_label)
        self.editor_tabs.setCurrentIndex(idx)
        self.editor_tabs.setTabToolTip(idx, file_path)

        self.path_to_editor[file_path] = viewer
        self.editor_to_path[viewer] = file_path

    def on_tab_close_requested(self, index):
        widget = self.editor_tabs.widget(index)
        if widget is None:
            return
        if widget == self.geom_view:
            self.editor_tabs.removeTab(index)
            # Não destrói a aba de geometria
            return
        editor = widget.editor if hasattr(widget, 'editor') else widget
        path = self.editor_to_path.get(editor)
        if path:
            del self.path_to_editor[path]
        if editor in self.editor_to_path:
            del self.editor_to_path[editor]
        self.editor_tabs.removeTab(index)
        widget.deleteLater()
    def save_file(self):
        editor = self.current_editor()
        if editor is None:
            return False
        path = self.editor_to_path.get(editor)
        if not path:
            return self.save_file_as()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(editor.toPlainText())
            self.log(f"Salvo: {path}\n")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao salvar:\n{e}")
            return False

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salvar arquivo como", "", "Todos os arquivos (*)")
        if not path:
            return False
        editor = self.current_editor()
        if editor is None:
            return False
        self.editor_to_path[editor] = path
        self.path_to_editor[path] = editor
        idx = self.editor_tabs.currentIndex()
        import os
        self.editor_tabs.setTabText(idx, os.path.basename(path))
        self.editor_tabs.setTabToolTip(idx, path)
        return self.save_file()

    def on_editor_text_changed(self):
        self.lint_current()

    def apply_scale(self):
        app = QApplication.instance()
        base_font = app.font()
        base_point = base_font.pointSize()
        if base_point <= 0:
            base_point = 10
        new_point = max(6, int(base_point * self.scale))
        new_font = QFont(base_font.family(), new_point)
        app.setFont(new_font)

        for editor in list(self.editor_to_path.keys()):
            try:
                f = editor.font()
                f.setPointSize(new_point)
                editor.setFont(f)
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
        palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ToolTipText, QColor("#161616"))
        palette.setColor(QPalette.Text, QColor("#161616"))
        palette.setColor(QPalette.Button, QColor("#e0e0e0"))
        palette.setColor(QPalette.ButtonText, QColor("#161616"))
        palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.Highlight, QColor("#0f62fe"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        app.setPalette(palette)

        app.setStyleSheet(
            """
            QMainWindow {
                background-color: #f8f9fa;
            }
            QWidget {
                background-color: #f8f9fa;
                color: #212529;
                font-family: "Segoe UI", "Inter", "Helvetica Neue", sans-serif;
            }
            QMenuBar {
                background-color: #ffffff;
                border-bottom: 1px solid #e9ecef;
                padding: 2px;
            }
            QMenuBar::item {
                spacing: 4px;
                padding: 6px 12px;
                background: transparent;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background: #f1f3f5;
                color: #212529;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #e8f0fe;
                color: #1a73e8;
            }
            QToolBar {
                background: #ffffff;
                border-bottom: 1px solid #e9ecef;
                spacing: 8px;
                padding: 6px 12px;
            }
            QToolButton, QPushButton {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                color: #495057;
            }
            QToolButton:hover, QPushButton:hover {
                background-color: #f1f3f5;
                border-color: #adb5bd;
                color: #212529;
            }
            QToolButton:pressed, QPushButton:pressed {
                background-color: #e9ecef;
                border-color: #868e96;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QListView, QTreeView, QComboBox {
                background-color: #ffffff;
                color: #212529;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px;
                selection-background-color: #1a73e8;
                selection-color: #ffffff;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QTreeView:focus, QComboBox:focus {
                border: 1.5px solid #1a73e8;
            }
            QTabWidget::pane {
                border: 1px solid #dee2e6;
                background: #ffffff;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #e9ecef;
                border: 1px solid #dee2e6;
                border-bottom: none;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                color: #495057;
                font-weight: 500;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #1a73e8;
                border-bottom: 1px solid #ffffff;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background: #dee2e6;
                color: #212529;
            }
            QStatusBar {
                border-top: 1px solid #e9ecef;
                background: #ffffff;
                padding: 4px;
            }
            QProgressBar {
                border: 1px solid #ced4da;
                background: #e9ecef;
                border-radius: 4px;
                text-align: center;
                font-weight: bold;
                font-size: 8pt;
            }
            QProgressBar::chunk {
                background-color: #1a73e8;
                border-radius: 3px;
            }
            QSplitter::handle {
                background: #dee2e6;
            }
            QSplitter::handle:horizontal {
                width: 3px;
            }
            QSplitter::handle:vertical {
                height: 3px;
            }
            QTreeView::item {
                padding: 4px;
            }
            QTreeView::item:hover {
                background-color: #f1f3f5;
            }
            QTreeView::item:selected {
                background-color: #e8f0fe;
                color: #1a73e8;
            }
            """
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

    def parse_residuals(self, text):
        import re
        import math
        res_dict = {}

        # Busca o tempo de simulação atual no log
        for m in re.finditer(r"\bTime\s*[=:]\s*([\d.eE+-]+)", text):
            try:
                self.current_sim_time = float(m.group(1))
            except ValueError:
                pass

        # Residuos do solver
        for m in re.finditer(r"Solving for (\w+), Initial residual = ([\d.eE+-]+)", text):
            var_name = m.group(1)
            try:
                res_dict[var_name] = float(m.group(2))
            except ValueError:
                pass

        # Mostra modulo da velocidade com os componentes disponiveis (2D ou 3D)
        u_components = [k for k in ("Ux", "Uy", "Uz") if k in res_dict]
        if u_components:
            try:
                umag = math.sqrt(sum(res_dict[k] ** 2 for k in u_components))
                for k in ("Ux", "Uy", "Uz"):
                    res_dict.pop(k, None)
                res_dict["|U|"] = umag
            except Exception:
                pass

        # yPlus stats: min/max/average
        for m in re.finditer(
            r"y\+\s*:\s*min\s*=\s*([\d.eE+-]+),\s*max\s*=\s*([\d.eE+-]+),\s*average\s*=\s*([\d.eE+-]+)",
            text
        ):
            try:
                res_dict["y+ min"] = float(m.group(1))
                res_dict["y+ max"] = float(m.group(2))
                res_dict["y+ avg"] = float(m.group(3))
            except ValueError:
                pass

        # Courant number
        for m in re.finditer(r"Courant Number mean:\s*([\d.eE+-]+)\s*max:\s*([\d.eE+-]+)", text):
            try:
                res_dict["Co mean"] = float(m.group(1))
                res_dict["Co max"] = float(m.group(2))
            except ValueError:
                pass

        # deltaT
        for m in re.finditer(r"deltaT\s*=\s*([\d.eE+-]+)", text):
            try:
                res_dict["deltaT"] = float(m.group(1))
            except ValueError:
                pass

        # Vazao/velocidade media de functionObject custom
        for m in re.finditer(
            r"Time:[^|\n]*\|\s*Area:\s*([\d.eE+-]+)\s*\|\s*Q:\s*([\d.eE+-]+)\s*\|\s*U_mean:\s*([\d.eE+-]+)",
            text
        ):
            try:
                res_dict["Area"] = float(m.group(1))
                res_dict["Q"] = float(m.group(2))
                res_dict["U_mean"] = float(m.group(3))
            except ValueError:
                pass

        # min/max de U e p vindos de volFieldValue
        for m in re.finditer(r"minMag\(\)\s+of\s+U\s*=\s*([\d.eE+-]+)", text):
            try:
                res_dict["U minMag"] = float(m.group(1))
            except ValueError:
                pass
        for m in re.finditer(r"maxMag\(\)\s+of\s+U\s*=\s*([\d.eE+-]+)", text):
            try:
                res_dict["U maxMag"] = float(m.group(1))
            except ValueError:
                pass
        for m in re.finditer(r"min\(\)\s+of\s+p\s*=\s*([\d.eE+-]+)", text):
            try:
                res_dict["p min"] = float(m.group(1))
            except ValueError:
                pass
        for m in re.finditer(r"max\(\)\s+of\s+p\s*=\s*([\d.eE+-]+)", text):
            try:
                res_dict["p max"] = float(m.group(1))
            except ValueError:
                pass

        if res_dict:
            self.residuals_view.update_residuals(res_dict, getattr(self, 'current_sim_time', None))
            for name, val in res_dict.items():
                self.convergence_monitor.update_residual(name, val)

    def _run_command_in_case(self, command, args=None, follow_solver_log=False):
        from PySide6.QtWidgets import QMessageBox
        if not getattr(self, 'current_case', None):
            QMessageBox.warning(self, "Aviso", "Nenhum caso aberto. Selecione um caso antes de executar este comando.")
            return
        if args is None:
            args = []
        if self.detached_run_active and self.current_case:
            alive = self._find_case_related_processes(self.current_case)
            alive.discard(os.getpid())
            if alive:
                self.log(
                    "Há processos do caso ainda em execução (background). "
                    "Use Parar antes de iniciar novo comando.\n"
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
            self.log("Outro processo está em execução. Aguarde o término.\n")
            return
        self.process.setWorkingDirectory(self.current_case)
        self.log(f"$ {command} {' '.join(args)}\n")
        
        if follow_solver_log:
            self.residuals_view.setVisible(True)
            self.show_tab("Simulação")
        else:
            self.residuals_view.setVisible(False)
            self.show_tab("Console")
            
        try:
            self.process.start(command, args)
        except Exception as e:
            self.log(f"Falha ao iniciar {command}: {e}\n")

    def stop_process(self):
        running = self.process.state() != QProcess.NotRunning
        detached = self.detached_run_active
        if not running and not detached:
            return
        try:
            self.log("Solicitando parada do processo...\n")
            targets = set()

            if running:
                root_pid = int(self.process.processId())

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
                targets.add(root_pid)

            if detached and self.current_case:
                targets.update(self._find_case_related_processes(self.current_case))

            targets.discard(os.getpid())

            for pid in sorted(targets, reverse=True):
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except Exception:
                    pass

            if running and not self.process.waitForFinished(2500):
                self.log("Forçando encerramento do processo e filhos...\n")
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
            self.log(f"Erro ao parar processo: {e}\n")

    def _on_process_started(self):
        try:
            self.status_label.setText("Running")
            self.status_progress.setVisible(True)
            self.run_action.setEnabled(False)
            self.stop_action.setEnabled(True)
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
                self.stop_action.setEnabled(True)
                self.log_follow_timer.start()
                return
            self.log_follow_timer.stop()
            self._set_idle_ui()
        except Exception:
            pass

    def run_blockMesh(self):
        self._run_command_in_case('blockMesh')

    def run_checkMesh(self):
        self._run_command_in_case('checkMesh')

    def run_snappyHexMesh(self):
        self._run_command_in_case('snappyHexMesh')

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

    def run_simulation(self):
        """Executa `./Allrun` dentro do diretório do caso, se existir.

        Usa um shell para permitir scripts com redirecionamentos e chamadas internas.
        """
        from PySide6.QtWidgets import QMessageBox
        import os, stat

        case = getattr(self, 'current_case', None)
        if not case:
            QMessageBox.warning(self, "Aviso", "Nenhum caso aberto. Selecione um caso antes de executar a simulação.")
            return

        allrun_path = os.path.join(case, 'Allrun')
        if not os.path.exists(allrun_path):
            try:
                content = (
                    "#!/bin/bash\n"
                    "cd ${0%/*} || exit 1\n"
                    "rm -rf processor*\n"
                    "decomposePar\n"
                    "rm -f log.*\n"
                    ". $WM_PROJECT_DIR/bin/tools/RunFunctions\n\n"
                    "runParallel $(getApplication)\n"
                )
                with open(allrun_path, 'w') as f:
                    f.write(content)
                self.log("Allrun criado automaticamente.\n")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Não foi possível criar Allrun: {e}")
                return

        try:
            st = os.stat(allrun_path)
            if not (st.st_mode & stat.S_IXUSR):
                os.chmod(allrun_path, st.st_mode | stat.S_IXUSR)
        except Exception as e:
            self.log(f"Aviso: não foi possível tornar Allrun executável: {e}\n")

        self.log_follow_path = None
        self.log_follow_pos = 0
        self.log_follow_ino = None
        self.log_follow_shown_path = None
        self.current_sim_time = 0.0
        self.sim_log_view.clear()
        self._run_command_in_case('/bin/bash', ['-lc', f'./Allrun'], follow_solver_log=True)

    def _set_idle_ui(self):
        self.status_label.setText("Idle")
        self.status_progress.setVisible(False)
        self.run_action.setEnabled(True)
        self.stop_action.setEnabled(False)

    def _handle_process_finished_log(self):
        if self.follow_solver_log:
            self.log("\nAllrun finalizado; monitorando solver em background...\n")
        else:
            self.log("\nProcesso finalizado.\n")

    def _choose_solver_log_file(self):
        case = getattr(self, 'current_case', None)
        if not case:
            return None

        preferred = os.path.join(case, 'log.foam')
        if os.path.isfile(preferred):
            return preferred

        candidates = [
            p for p in glob.glob(os.path.join(case, 'log.*'))
            if os.path.isfile(p) and not p.endswith('.log')
        ]
        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)

    def _poll_solver_log(self):
        if not self.follow_solver_log:
            return

        if not self.log_follow_path or not os.path.isfile(self.log_follow_path):
            self.log_follow_path = self._choose_solver_log_file()
            self.log_follow_pos = 0
            self.log_follow_ino = None
            if self.log_follow_path:
                self.log(f"Monitorando resíduos em: {self.log_follow_path}\n")
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
        """Carrega limites de convergência do fvSolution."""
        self.targets = self.parse_residual_controls(case_path)
        self.table.setRowCount(0)

    def parse_residual_controls(self, case_path):
        """Analisa tolerâncias de residualControl no fvSolution."""
        import re
        sol_path = os.path.join(case_path, "system", "fvSolution")
        if not os.path.isfile(sol_path):
            return {}
        try:
            with open(sol_path, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(r'residualControl\s*\{', content)
            if not match:
                return {}
            start = match.end()
            brace = 1
            end = -1
            for idx in range(start, len(content)):
                c = content[idx]
                if c == '{':
                    brace += 1
                elif c == '}':
                    brace -= 1
                    if brace == 0:
                        end = idx
                        break
            if end == -1:
                return {}
            block = content[start:end]
            targets = {}
            for m in re.finditer(r'([a-zA-Z0-9_"\(\)\|\s\-]+)\s+([0-9eE\.\-]+)\s*;', block):
                key = m.group(1).strip().strip('"').strip("'")
                targets[key] = float(m.group(2))
            return targets
        except Exception:
            return {}

    def update_residual(self, name, val):
        """Atualiza a tabela com o resíduo mais recente de cada variável."""
        import re
        row = -1
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == name:
                row = r
                break
        if row == -1:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(name))
            
            # Procura tolerância correspondente
            target = 1e-5
            for key, target_val in self.targets.items():
                try:
                    if re.search(key, name):
                        target = target_val
                        break
                except Exception:
                    if key in name:
                        target = target_val
                        break
            self.table.setItem(row, 2, QTableWidgetItem(f"{target:.1e}"))
            
        item_val = QTableWidgetItem(f"{val:.2e}")
        
        # Compara com a meta
        try:
            target = float(self.table.item(row, 2).text())
        except ValueError:
            target = 1e-5
            
        if val <= target:
            item_val.setForeground(QColor("#137333")) # Verde
            item_val.setToolTip("Convergido!")
        else:
            item_val.setForeground(QColor("#d9381e")) # Vermelho
            
        self.table.setItem(row, 1, item_val)


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
        import re
        self.current_case_path = case_path
        if not case_path:
            self.setEnabled(False)
            return
            
        params = self.read_control_dict(case_path)
        if params:
            self.setEnabled(True)
            self.txt_app.setText(params.get("application", "-"))
            
            try:
                self.spin_endtime.setValue(float(params.get("endTime", "0")))
            except ValueError:
                self.spin_endtime.setValue(0)
                
            try:
                self.spin_deltat.setValue(float(params.get("deltaT", "0.001")))
            except ValueError:
                self.spin_deltat.setValue(0.001)
                
            try:
                self.spin_interval.setValue(float(params.get("writeInterval", "100")))
            except ValueError:
                self.spin_interval.setValue(100)
        else:
            self.setEnabled(False)

    def read_control_dict(self, case_path):
        import re
        dict_path = os.path.join(case_path, "system", "controlDict")
        if not os.path.isfile(dict_path):
            return {}
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                content = f.read()
            clean = re.sub(r'//.*', '', content)
            clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
            
            res = {}
            for key in ("endTime", "deltaT", "writeInterval", "application"):
                m = re.search(rf'\b{key}\s+([^;]+);', clean)
                if m:
                    res[key] = m.group(1).strip()
            return res
        except Exception:
            return {}

    def save_parameters(self):
        if not self.current_case_path:
            return
            
        values = {
            "endTime": str(self.spin_endtime.value()),
            "deltaT": str(self.spin_deltat.value()),
            "writeInterval": str(self.spin_interval.value())
        }
        
        if self.write_control_dict(self.current_case_path, values):
            QMessageBox.information(self, "Sucesso", "Parâmetros salvos com sucesso!")
            if hasattr(self.main_window, 'log'):
                self.main_window.log("Parâmetros do controlDict atualizados.\n")
                
            # Força recarga do arquivo no editor se estiver aberto
            dict_path = os.path.join(self.current_case_path, "system", "controlDict")
            if hasattr(self.main_window, 'path_to_editor'):
                editor = self.main_window.path_to_editor.get(dict_path)
                if editor:
                    try:
                        with open(dict_path, 'r', encoding='utf-8') as f:
                            editor.blockSignals(True)
                            editor.setPlainText(f.read())
                            editor.blockSignals(False)
                    except Exception:
                        pass
        else:
            QMessageBox.critical(self, "Erro", "Falha ao atualizar controlDict.")

    def write_control_dict(self, case_path, values):
        import re
        dict_path = os.path.join(case_path, "system", "controlDict")
        if not os.path.isfile(dict_path):
            return False
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            for key, val in values.items():
                pattern = rf'(\b{key}\s+)[^;]+(\s*;)'
                content = re.sub(pattern, rf'\g<1>{val}\g<2>', content)
                
            with open(dict_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception:
            return False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
