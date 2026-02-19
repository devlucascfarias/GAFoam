from abc import ABC, abstractmethod


class Module(ABC):
    """Base class para módulos.

    Um módulo pode registrar menus, toolbars, docks e ações na janela principal.
    """
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def register(self, window):
        """Registra o módulo na `window` (MainWindow)."""

    def unregister(self, window):
        """Opcional: desfaz o registro (remover menus/toolbars)."""
        return
