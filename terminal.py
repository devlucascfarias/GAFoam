from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLineEdit
from PySide6.QtCore import QProcess, QProcessEnvironment
from PySide6.QtGui import QTextCursor
import re
import html

ANSI_COLORS = {
    '30': 'black',
    '31': 'red',
    '32': 'green',
    '33': 'yellow',
    '34': 'blue',
    '35': 'magenta',
    '36': 'cyan',
    '37': 'white',
    '90': '#555',
    '91': '#ff5555',
    '92': '#55ff55',
    '93': '#ffff55',
    '94': '#5555ff',
    '95': '#ff55ff',
    '96': '#55ffff',
    '97': '#ffffff',
}

ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")


class TerminalWidget(QWidget):
    """Simple embedded terminal: a read-only output area plus a single-line input.

    Starts an interactive bash process and forwards user input to it. Also
    exposes an `append()` method so existing code that calls `log_view.append(...)`
    continues to work.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.input = QLineEdit()
        self.input.setPlaceholderText('Comando (Enter para enviar)')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output)
        layout.addWidget(self.input)

        self.shell = QProcess(self)

        self.shell.setProcessChannelMode(QProcess.MergedChannels)
        self.shell.readyReadStandardOutput.connect(self._on_ready)
        self.shell.started.connect(self._on_started)
        self.shell.finished.connect(lambda code, status: self.append(f"\n[bash] exited ({code})\n"))

        try:
            env = QProcessEnvironment.systemEnvironment()

            env.insert('PS1', '\\x1b[1;32m\\u@\\h:\\w\\$ \\x1b[0m')
            self.shell.setProcessEnvironment(env)
            self.shell.start('/bin/bash', ['-i'])
        except Exception:

            pass

        self.input.returnPressed.connect(self._on_enter)

    def closeEvent(self, event):

        if self.shell and self.shell.state() != QProcess.NotRunning:
            self.shell.terminate()
            if not self.shell.waitForFinished(1000):
                self.shell.kill()
        super().closeEvent(event)

    def _on_started(self):
        pass

    def _on_ready(self):
        try:
            data = self.shell.readAllStandardOutput().data().decode(errors='replace')
            if data:

                clean = data
                clean = re.sub(r'\x1b\].*?\x07', '', clean)
                clean = re.sub(r'\x1b\[(?![0-9;]*m)[0-9;?]*[A-Za-z]', '', clean)
                clean = clean.replace('\x07', '')
                clean = clean.replace('\r', '')
                html_text = self.ansi_to_html(clean)
                self.insert_html(html_text)
        except Exception:
            pass

    def _on_enter(self):
        cmd = self.input.text()

        try:
            if cmd:
                self.append(f"$ {cmd}\n")
                self.shell.write((cmd + "\n").encode())
            else:

                self.shell.write(b"\n")
        except Exception:

            if cmd:
                self.append(f"$ {cmd}\n")
        self.input.clear()

    def append(self, text: str):

        safe = html.escape(text).replace('\n', '<br>')
        self.insert_html(safe)

    def insert_html(self, html_text: str):
        try:
            if not self.output or not hasattr(self.output, "moveCursor"):
                return
            self.output.moveCursor(QTextCursor.End)
        except (RuntimeError, AttributeError):

            return
        except Exception:
            try:
                tc = self.output.textCursor()
                tc.movePosition(QTextCursor.End)
                self.output.setTextCursor(tc)
            except Exception:
                return

        try:
            self.output.insertHtml(html_text)
            v = self.output.verticalScrollBar()
            v.setValue(v.maximum())
        except (RuntimeError, AttributeError):
            pass
        except Exception:

            try:
                self.output.insertPlainText(html.unescape(re.sub('<br>', '\n', re.sub('<[^>]+>', '', html_text))))
            except Exception:
                pass

    def ansi_to_html(self, text: str) -> str:

        html_parts = []
        last = 0
        current_style = {}

        for m in ANSI_RE.finditer(text):
            chunk = text[last:m.start()]
            if chunk:
                html_parts.append(html.escape(chunk).replace('\n', '<br>'))
            codes = m.group(1)
            if not codes:
                codes = '0'
            for code in codes.split(';'):
                if code == '0':
                    current_style = {}
                elif code == '1':
                    current_style['font-weight'] = 'bold'
                elif code in ANSI_COLORS:
                    current_style['color'] = ANSI_COLORS[code]

            if current_style:
                style = ';'.join(f'{k}:{v}' for k, v in current_style.items())
                html_parts.append(f"<span style=\"{style}\">")
            else:

                html_parts.append('</span>')
            last = m.end()

        rem = text[last:]
        if rem:
            html_parts.append(html.escape(rem).replace('\n', '<br>'))

        out = ''.join(html_parts)
        out = out.replace('</span><span', '<span')

        if out.startswith('</span>'):
            out = out[len('</span>'):]
        return out

    def _on_started(self):

        return
