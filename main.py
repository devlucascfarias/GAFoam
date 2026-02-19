from main_window import MainWindow
from PySide6.QtWidgets import QApplication
import sys

def main():
    """Ponto de entrada da aplicação."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()