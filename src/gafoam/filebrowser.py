import os
from PySide6.QtWidgets import QTreeView, QFileSystemModel, QHeaderView, QFileIconProvider
from PySide6.QtCore import Qt, QSize, QFileInfo
from PySide6.QtGui import QIcon
from gafoam.resources import icon_path


class FoamFileIconProvider(QFileIconProvider):
    """Provedor de ícones multiplataforma para o explorador de arquivos OpenFOAM.
    
    Garante renderização perfeita em ambientes Linux/Ubuntu/WSL sem dependência de temas XDG.
    """

    def __init__(self):
        super().__init__()
        self._cache = {}

    def _get_icon(self, name):
        if name not in self._cache:
            p = icon_path(name)
            if os.path.isfile(p):
                self._cache[name] = QIcon(p)
            else:
                self._cache[name] = QIcon()
        return self._cache[name]

    def icon(self, type_or_info):
        if isinstance(type_or_info, QFileInfo):
            info = type_or_info
            fname = info.fileName().lower()
            suffix = info.suffix().lower()

            if info.isDir():
                return self._get_icon("folder.svg")

            if suffix in ("stl", "obj"):
                return self._get_icon("file_mesh.svg")
            elif suffix == "pdf":
                return self._get_icon("file_pdf.svg")
            elif suffix == "foam":
                return self._get_icon("file_foam.svg")
            elif suffix in ("sh", "py") or fname in ("allrun", "allclean", "mesh.sh"):
                return self._get_icon("file_script.svg")
            elif fname.endswith("dict") or fname in ("fvschemes", "fvsolution", "controldict", "blockmeshdict"):
                return self._get_icon("file_dict.svg")
            elif fname.startswith("log.") or suffix == "log":
                return self._get_icon("cmd_dollar.svg")
            else:
                return self._get_icon("file_generic.svg")

        elif isinstance(type_or_info, QFileIconProvider.IconType):
            if type_or_info in (QFileIconProvider.Folder, QFileIconProvider.Drive):
                return self._get_icon("folder.svg")
            return self._get_icon("file_generic.svg")

        return super().icon(type_or_info)


class FileBrowser:
    """Componente de explorador de arquivos com ícones nativos multiplataforma."""

    def __init__(self, scale=1.0, parent=None):
        self.scale = scale
        self.file_model = QFileSystemModel(parent)
        self.icon_provider = FoamFileIconProvider()
        self.file_model.setIconProvider(self.icon_provider)
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
        self.file_view.setIconSize(QSize(int(18 * self.scale), int(18 * self.scale)))

    def set_root(self, path):
        self.file_view.setRootIndex(self.file_model.index(path))

    def set_click_callback(self, callback):
        self.file_view.clicked.connect(callback)

