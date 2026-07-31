from PySide6.QtWidgets import QTreeView, QFileSystemModel, QHeaderView
from PySide6.QtCore import Qt, QSize


class FileBrowser:
    """Componente simples de explorador de arquivos usado pela UI principal.

    Exposição mínima: `file_model`, `file_view`, `set_root(path)`, `set_click_callback(cb)`.
    """
    def __init__(self, scale=1.0, parent=None):
        self.scale = scale
        self.file_model = QFileSystemModel(parent)
        self.file_model.setRootPath("")

        self.file_view = QTreeView(parent)
        self.file_view.setModel(self.file_model)
        self.file_view.setRootIndex(self.file_model.index(""))

        self.file_view.setHeaderHidden(False)
        self.file_view.setTextElideMode(Qt.ElideNone)
        header = self.file_view.header()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        try:
            header.resizeSection(0, int(400 * self.scale))
        except Exception:
            pass
        self.file_view.setAnimated(True)
        self.file_view.setSortingEnabled(True)
        self.file_view.setMinimumWidth(int(260 * self.scale))
        self.file_view.setIconSize(QSize(int(20 * self.scale), int(20 * self.scale)))

    def set_root(self, path):
        self.file_view.setRootIndex(self.file_model.index(path))

    def set_click_callback(self, callback):
        self.file_view.clicked.connect(callback)
