from PySide6.QtGui import QAction, QKeySequence


def setup_menus(window):
    """Configura os menus principais na `window` passada (mutates window)."""
    menubar = window.menuBar()

    save_action = QAction("Save", window)
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_action.setStatusTip("Save current file (Ctrl+S)")
    save_action.triggered.connect(lambda: getattr(window, 'save_file', lambda: None)())
    window.addAction(save_action)

    save_as_action = QAction("Save As", window)
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    save_as_action.setStatusTip("Save as... (Ctrl+Shift+S)")
    save_as_action.triggered.connect(lambda: getattr(window, 'save_file_as', lambda: None)())
    window.addAction(save_as_action)

    zoom_reset_action = QAction("Reset Zoom", window)
    zoom_reset_action.triggered.connect(window.zoom_reset)
    zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
    zoom_reset_action.setStatusTip("Reset scale (Ctrl+0)")
    window.addAction(zoom_reset_action)

    def safe_call(fn_name):
        def _call():
            editor = getattr(window, 'current_editor', lambda: None)()
            if editor is None:
                return
            getattr(editor, fn_name)()
        return _call

    cut_action = QAction("Cut", window)
    cut_action.setShortcut(QKeySequence.Cut)
    cut_action.triggered.connect(safe_call('cut'))
    window.addAction(cut_action)

    copy_action = QAction("Copy", window)
    copy_action.setShortcut(QKeySequence.Copy)
    copy_action.triggered.connect(safe_call('copy'))
    window.addAction(copy_action)

    paste_action = QAction("Paste", window)
    paste_action.setShortcut(QKeySequence.Paste)
    paste_action.triggered.connect(safe_call('paste'))
    window.addAction(paste_action)

    undo_action = QAction("Undo", window)
    undo_action.setShortcut(QKeySequence.Undo)
    undo_action.triggered.connect(safe_call('undo'))
    window.addAction(undo_action)

    redo_action = QAction("Redo", window)
    redo_action.setShortcut(QKeySequence.Redo)
    redo_action.triggered.connect(safe_call('redo'))
    window.addAction(redo_action)

    menubar.setVisible(False)

