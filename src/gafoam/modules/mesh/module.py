from PySide6.QtWidgets import QToolBar, QMessageBox
from PySide6.QtGui import QAction, QIcon
from ..base import Module
import os


class MeshModule(Module):
    def __init__(self):
        super().__init__("Mesh")
        self.toolbar = None
        self.menu = None

    def _icon_path(self, name):
        base = os.path.join(os.path.dirname(__file__), 'icons')
        return os.path.join(base, name)

    def register(self, window):
        # adiciona menu Mesh
        menubar = window.menuBar()
        mesh_menu = menubar.addMenu("Mesh")

        block_action = QAction(QIcon(self._icon_path('block.svg')), "blockMesh", window)
        block_action.setStatusTip("Executar blockMesh no caso atual")
        block_action.triggered.connect(window.run_blockMesh)
        mesh_menu.addAction(block_action)

        check_action = QAction(QIcon(self._icon_path('check.svg')), "checkMesh", window)
        check_action.setStatusTip("Executar checkMesh no caso atual")
        check_action.triggered.connect(window.run_checkMesh)
        mesh_menu.addAction(check_action)

        snappy_action = QAction(QIcon(self._icon_path('snappy.svg')), "snappyHexMesh", window)
        snappy_action.setStatusTip("Executar snappyHexMesh no caso atual")
        snappy_action.triggered.connect(window.run_snappyHexMesh)
        mesh_menu.addAction(snappy_action)

        # toolbar do módulo
        try:
            tb = QToolBar("Mesh")
            tb.addAction(block_action)
            tb.addAction(check_action)
            tb.addAction(snappy_action)
            window.addToolBar(tb)
            self.toolbar = tb
        except Exception:
            # ambientes headless podem falhar ao criar toolbars
            pass

        self.menu = mesh_menu

    def unregister(self, window):
        try:
            if self.toolbar:
                window.removeToolBar(self.toolbar)
            if self.menu:
                window.menuBar().removeAction(self.menu.menuAction())
        except Exception:
            pass
