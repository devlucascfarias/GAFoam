import sys
import os
import signal
import subprocess
import glob
import time
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QTextEdit, QPlainTextEdit, QVBoxLayout, QWidget, QMenuBar, QMenu, QSplitter, QTabWidget, QFileDialog, QMessageBox, QToolBar, QLabel, QProgressBar
from PySide6.QtGui import QAction, QIcon, QFont, QKeySequence, QPalette, QColor, QTextCharFormat, QPainter, QTextCursor
from PySide6.QtCore import QProcess, Qt, QSize, QRegularExpression, QRect, QTimer
from editor import CodeEditor, SimpleHighlighter
from filebrowser import FileBrowser
from stl_viewer import STLViewer
from residuals import ResidualsWidget
from menus import setup_menus
from handlers import make_stdout_handler, make_stderr_handler, make_finished_handler
from terminal import TerminalWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interface OpenFOAM")
        self.resize(600, 400)


        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self.on_tab_close_requested)

        self.path_to_editor = {}
        self.editor_to_path = {}
        self.current_case = None

        self.tab_widget = QTabWidget()
        self.log_view = TerminalWidget(parent=self)
        self.tab_widget.addTab(self.log_view, "Terminal")

        self.sim_log_view = QTextEdit(parent=self)
        self.sim_log_view.setReadOnly(True)
        self.residuals_view = ResidualsWidget(parent=self)

        self.logs_panel = QWidget(parent=self)
        logs_layout = QVBoxLayout(self.logs_panel)
        logs_layout.setContentsMargins(0, 0, 0, 0)
        self.logs_splitter = QSplitter(Qt.Horizontal)
        self.logs_splitter.addWidget(self.sim_log_view)
        self.logs_splitter.addWidget(self.residuals_view)
        self.logs_splitter.setStretchFactor(0, 1)
        self.logs_splitter.setStretchFactor(1, 1)
        logs_layout.addWidget(self.logs_splitter)
        self.tab_widget.addTab(self.logs_panel, "Logs")

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self.editor_tabs)
        right_splitter.addWidget(self.tab_widget)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)

        setup_menus(self)

        try:
            self.toolbar = QToolBar("Run")
            self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.addToolBar(self.toolbar)

            case_icon = QIcon.fromTheme('folder-open')
            case_act = QAction(case_icon, 'Abrir Caso', self)
            case_act.setToolTip('Selecionar Caso')
            case_act.setStatusTip('Selecionar a pasta do caso OpenFOAM')
            case_act.triggered.connect(self.selecionar_caso)
            self.toolbar.addAction(case_act)
            sep_case = QLabel('|')
            sep_case.setContentsMargins(6, 0, 6, 0)
            self.toolbar.addWidget(sep_case)

            run_icon = QIcon.fromTheme('media-playback-start')
            stop_icon = QIcon.fromTheme('media-playback-stop')

            self.run_action = QAction(run_icon, 'Allrun', self)
            self.run_action.setToolTip('Rodar (Ctrl+R)')
            self.run_action.setStatusTip('Rodar simulação (Allrun)')
            self.run_action.setShortcut(QKeySequence('Ctrl+R'))
            self.run_action.triggered.connect(self.run_simulation)
            self.toolbar.addAction(self.run_action)

            self.stop_action = QAction(stop_icon, 'Parar', self)
            self.stop_action.setToolTip('Parar')
            self.stop_action.setStatusTip('Parar processo em execução')
            self.stop_action.triggered.connect(self.stop_process)
            self.stop_action.setEnabled(False)
            self.toolbar.addAction(self.stop_action)
        except Exception:
            pass

        try:
            sep_label = QLabel('|')
            sep_label.setContentsMargins(6, 0, 6, 0)
            self.toolbar.addWidget(sep_label)

            block_icon = QIcon.fromTheme('application-x-executable')
            block_act = QAction(block_icon, 'blockMesh', self)
            block_act.setStatusTip('Executar blockMesh')
            block_act.triggered.connect(self.run_blockMesh)
            self.toolbar.addAction(block_act)

            check_icon = QIcon.fromTheme('dialog-ok')
            check_act = QAction(check_icon, 'checkMesh', self)
            check_act.setStatusTip('Executar checkMesh')
            check_act.triggered.connect(self.run_checkMesh)
            self.toolbar.addAction(check_act)

            snappy_icon = QIcon.fromTheme('system-run')
            snappy_act = QAction(snappy_icon, 'snappyHexMesh', self)
            snappy_act.setStatusTip('Executar snappyHexMesh')
            snappy_act.triggered.connect(self.run_snappyHexMesh)
            self.toolbar.addAction(snappy_act)
        except Exception:
            pass

        self.scale = 1.0

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
        self.log_view.append(f"Caso aberto: {dir_path}")
        self.file_browser.set_root(dir_path)
        self.current_case = dir_path

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
        return w if isinstance(w, CodeEditor) else None

    def open_file_in_tab(self, file_path, text):
        import os
        if file_path in self.path_to_editor:
            editor = self.path_to_editor[file_path]
            idx = self.editor_tabs.indexOf(editor)
            if idx != -1:
                self.editor_tabs.setCurrentIndex(idx)
                return
        editor = CodeEditor()
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
        idx = self.editor_tabs.addTab(editor, tab_label)
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
        path = self.editor_to_path.get(widget)
        if path:
            del self.path_to_editor[path]
        if widget in self.editor_to_path:
            del self.editor_to_path[widget]
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
            self.log_view.append(f"Salvo: {path}")
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
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(250, 250, 250))
        palette.setColor(QPalette.WindowText, QColor(10, 10, 10))
        palette.setColor(QPalette.Base, QColor(245, 245, 245))
        palette.setColor(QPalette.AlternateBase, QColor(250, 250, 250))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
        palette.setColor(QPalette.ToolTipText, QColor(10, 10, 10))
        palette.setColor(QPalette.Text, QColor(10, 10, 10))
        palette.setColor(QPalette.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ButtonText, QColor(10, 10, 10))
        palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        app.setPalette(palette)

    def wheelEvent(self, event):
        super().wheelEvent(event)

    def zoom_in(self):
        self.scale *= 1.15
        self.apply_scale()

    def zoom_out(self):
        self.scale = max(0.5, self.scale / 1.15)
        self.apply_scale()

    def zoom_reset(self):
        self.scale = 1.2
        self.apply_scale()



    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.log_view.append(data)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.log_view.append(f"[ERR] {data}")

    def process_finished(self):
        self.log_view.append("\nProcesso finalizado.")

    def parse_residuals(self, text):
        import re
        import math
        pattern = r"Solving for (\w+), Initial residual = ([\d.e+-]+)"
        matches = re.finditer(pattern, text)
        res_dict = {}
        for m in matches:
            var_name = m.group(1)
            value = m.group(2)
            try:
                res_dict[var_name] = float(value)
            except ValueError:
                pass

        # Mostra modulo da velocidade em vez de componentes Ux/Uy/Uz.
        u_components = ("Ux", "Uy", "Uz")
        if all(k in res_dict for k in u_components):
            umag = math.sqrt(
                res_dict["Ux"] ** 2 + res_dict["Uy"] ** 2 + res_dict["Uz"] ** 2
            )
            for k in u_components:
                res_dict.pop(k, None)
            res_dict["|U|"] = umag
        else:
            for k in u_components:
                res_dict.pop(k, None)

        if res_dict:
            self.residuals_view.update_residuals(res_dict)

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
                self.log_view.append(
                    "Há processos do caso ainda em execução (background). "
                    "Use Parar antes de iniciar novo comando."
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
            self.log_view.append("Outro processo está em execução. Aguarde o término.")
            return
        self.process.setWorkingDirectory(self.current_case)
        self.log_view.append(f"Executando: {command} {' '.join(args)} (cwd={self.current_case})")
        try:
            self.process.start(command, args)
        except Exception as e:
            self.log_view.append(f"Falha ao iniciar {command}: {e}")

    def stop_process(self):
        running = self.process.state() != QProcess.NotRunning
        detached = self.detached_run_active
        if not running and not detached:
            return
        try:
            self.log_view.append("Solicitando parada do processo...")
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
                self.log_view.append("Forçando encerramento do processo e filhos...")
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
            self.log_view.append(f"Erro ao parar processo: {e}")

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
                self.log_view.append("Allrun criado automaticamente.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Não foi possível criar Allrun: {e}")
                return

        try:
            st = os.stat(allrun_path)
            if not (st.st_mode & stat.S_IXUSR):
                os.chmod(allrun_path, st.st_mode | stat.S_IXUSR)
        except Exception as e:
            self.log_view.append(f"Aviso: não foi possível tornar Allrun executável: {e}")

        self.log_follow_path = None
        self.log_follow_pos = 0
        self.log_follow_ino = None
        self.log_follow_shown_path = None
        self.sim_log_view.clear()
        self._run_command_in_case('/bin/bash', ['-lc', f'./Allrun'], follow_solver_log=True)

    def _set_idle_ui(self):
        self.status_label.setText("Idle")
        self.status_progress.setVisible(False)
        self.run_action.setEnabled(True)
        self.stop_action.setEnabled(False)

    def _handle_process_finished_log(self):
        if self.follow_solver_log:
            self.log_view.append("\nAllrun finalizado; monitorando solver em background...\n")
        else:
            self.log_view.append("\nProcesso finalizado.\n")

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
                self.log_view.append(f"Monitorando resíduos em: {self.log_follow_path}")
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
                    self.log_view.append("\nProcesso finalizado (log estabilizado).\n")
        except Exception:
            pass

    def _append_sim_log(self, text):
        if not text:
            return
        try:
            self.sim_log_view.moveCursor(QTextCursor.End)
            self.sim_log_view.insertPlainText(text)
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
