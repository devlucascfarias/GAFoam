from PySide6.QtGui import QAction, QKeySequence


def setup_menus(window):
    """Configura os menus principais na `window` passada (mutates window)."""
    menubar = window.menuBar()

    save_action = QAction("Salvar", window)
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_action.setStatusTip("Salvar arquivo atual (Ctrl+S)")
    save_action.triggered.connect(lambda: getattr(window, 'save_file', lambda: None)())
    window.addAction(save_action)

    save_as_action = QAction("Salvar Como", window)
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    save_as_action.setStatusTip("Salvar como... (Ctrl+Shift+S)")
    save_as_action.triggered.connect(lambda: getattr(window, 'save_file_as', lambda: None)())
    window.addAction(save_as_action)

    menubar.addMenu("Comandos")

    view_menu = menubar.addMenu("Visualizar")
    zoom_reset_action = QAction("Resetar Escala", window)
    zoom_reset_action.triggered.connect(window.zoom_reset)
    zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
    zoom_reset_action.setStatusTip("Resetar a escala (Ctrl+0)")
    view_menu.addAction(zoom_reset_action)

    edit_menu = menubar.addMenu("Editar")
    def safe_call(fn_name):
        def _call():
            editor = getattr(window, 'current_editor', lambda: None)()
            if editor is None:
                return
            getattr(editor, fn_name)()
        return _call

    cut_action = QAction("Cortar", window)
    cut_action.setShortcut(QKeySequence.Cut)
    cut_action.triggered.connect(safe_call('cut'))
    edit_menu.addAction(cut_action)

    copy_action = QAction("Copiar", window)
    copy_action.setShortcut(QKeySequence.Copy)
    copy_action.triggered.connect(safe_call('copy'))
    edit_menu.addAction(copy_action)

    paste_action = QAction("Colar", window)
    paste_action.setShortcut(QKeySequence.Paste)
    paste_action.triggered.connect(safe_call('paste'))
    edit_menu.addAction(paste_action)

    undo_action = QAction("Desfazer", window)
    undo_action.setShortcut(QKeySequence.Undo)
    undo_action.triggered.connect(safe_call('undo'))
    edit_menu.addAction(undo_action)

    redo_action = QAction("Refazer", window)
    redo_action.setShortcut(QKeySequence.Redo)
    redo_action.triggered.connect(safe_call('redo'))
    edit_menu.addAction(redo_action)
