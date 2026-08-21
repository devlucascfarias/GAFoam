import os
import sys

# Garante compatibilidade do pipeline VTK com o servidor gráfico X11/WSLg
if sys.platform.startswith("linux"):
    os.environ.setdefault("VTK_DISABLE_SHM", "1")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from gafoam.main_window import MainWindow
from gafoam.resources import load_application_fonts


def run(argv=None):
    """Sobe a interface e devolve o código de saída do loop de eventos."""
    app = QApplication(argv if argv is not None else sys.argv)
    try:
        app.setAttribute(Qt.AA_DontShowIconsInMenus, False)
    except Exception:
        pass
    load_application_fonts()

    # Define Inter como a fonte padrão de toda a aplicação
    default_font = QFont("Inter", 10)
    default_font.setStyleHint(QFont.SansSerif)
    app.setFont(default_font)

    window = MainWindow()
    window.show()
    return app.exec()

