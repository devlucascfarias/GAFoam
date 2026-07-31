"""Inicialização da aplicação."""

import sys

from PySide6.QtWidgets import QApplication

from gafoam.main_window import MainWindow


def run(argv=None):
    """Sobe a interface e devolve o código de saída do loop de eventos."""
    app = QApplication(argv if argv is not None else sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
