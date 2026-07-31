"""Janela principal da aplicação: layout, execução de comandos e monitoramento."""

import os
import signal
import stat
import subprocess
import time

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPlainTextEdit,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QMenu,
    QSplitter,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QToolBar,
    QLabel,
    QProgressBar,
    QToolButton,
)
from PySide6.QtGui import QAction, QIcon, QFont, QKeySequence, QPalette, QColor, QTextCursor
from PySide6.QtCore import QProcess, Qt, QSize, QTimer

from gafoam import foamdict, logparse
from gafoam.editor import EditorContainerWidget, SimpleHighlighter
from gafoam.filebrowser import FileBrowser
from gafoam.handlers import make_stdout_handler, make_stderr_handler, make_finished_handler
from gafoam.menus import setup_menus
from gafoam.panels import ControlDictDockWidget, ConvergenceMonitorWidget
from gafoam.residuals import ResidualsWidget
from gafoam.resources import icon_path
from gafoam.stl_viewer import CaseGeometryWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interface OpenFOAM")
        self.resize(1024, 768)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self.on_tab_close_requested)

        # A geometria é um painel sob demanda: só vira aba quando o usuário
        # abre um arquivo de malha, para não ocupar o editor por padrão.
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
        """Ícone do pacote, com fallback para o tema do sistema."""
        path = icon_path(filename)
        if os.path.isfile(path):
            return QIcon(path)
        if fallback_theme:
            return QIcon.fromTheme(fallback_theme)
        return QIcon()

    def selecionar_caso(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Selecione a pasta do caso OpenFOAM")
        if not dir_path:
            return
        missing = foamdict.validate_case_dirs(dir_path)
        if missing:
            QMessageBox.critical(self, "Erro", f"A pasta selecionada não contém as subpastas obrigatórias: {', '.join(missing)}")
            return
        self.log(f"Caso aberto: {dir_path}\n")
        self.show_tab("Console")
        self.file_browser.set_root(dir_path)
        self.current_case = dir_path
        self.geom_scanned_case = None
        if self.editor_tabs.indexOf(self.geom_view) != -1:
            # Painel já aberto: recarrega para refletir o novo caso.
            self.show_geometry()
        self.control_dock.load_case(dir_path)
        self.convergence_monitor.load_case(dir_path)

        QMessageBox.information(self, "Sucesso", f"Caso OpenFOAM aberto com sucesso!\n{dir_path}")
    def on_file_clicked(self, index):

        if not index.isValid():
            return
        if self.file_browser.file_model.isDir(index):
            return
        file_path = self.file_browser.file_model.filePath(index)

        if file_path.lower().endswith((".stl", ".obj")):
            self.show_geometry(file_path)
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

    def show_geometry(self, file_path=None):
        """Abre o painel de geometria, destacando a malha informada.

        A aba é criada na primeira chamada e reaproveitada nas seguintes; o
        caso só é varrido quando o painel é realmente exibido.
        """
        index = self.editor_tabs.indexOf(self.geom_view)
        if index == -1:
            index = self.editor_tabs.addTab(self.geom_view, "Geometria")
            self.editor_tabs.setTabToolTip(index, "Visualização das malhas do caso")

        if self.current_case and self.geom_scanned_case != self.current_case:
            self.geom_view.scan_case(self.current_case)
            self.geom_scanned_case = self.current_case

        self.editor_tabs.setCurrentIndex(index)

        if file_path and not self.geom_view.select_mesh(file_path):
            # Arquivo fora da varredura (caso não aberto ou malha recém-criada).
            self.geom_view.viewer.load_meshes([(os.path.basename(file_path), file_path)])

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
        """Extrai grandezas do log e as encaminha ao gráfico e ao monitor."""
        values, sim_time = logparse.parse_residuals(text)
        if sim_time is not None:
            self.current_sim_time = sim_time
        if not values:
            return
        self.residuals_view.update_residuals(values, getattr(self, 'current_sim_time', None))
        for name, val in values.items():
            self.convergence_monitor.update_residual(name, val)

    def _run_command_in_case(self, command, args=None, follow_solver_log=False):
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
