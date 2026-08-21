"""Localização dos assets empacotados junto ao código."""

import os

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def icon_path(filename):
    """Caminho absoluto de um ícone do pacote (o arquivo pode não existir)."""
    return os.path.join(ICONS_DIR, filename)


def has_icon(filename):
    """Indica se o ícone está presente no pacote."""
    return os.path.isfile(icon_path(filename))


def font_path(filename):
    """Caminho absoluto de uma fonte do pacote."""
    return os.path.join(FONTS_DIR, filename)


def load_application_fonts():
    """Registra as fontes empacotadas no QFontDatabase global da aplicação."""
    try:
        from PySide6.QtGui import QFontDatabase
    except ImportError:
        return []

    loaded_families = []
    if os.path.isdir(FONTS_DIR):
        for fname in os.listdir(FONTS_DIR):
            if fname.lower().endswith((".ttf", ".otf")):
                fpath = os.path.join(FONTS_DIR, fname)
                font_id = QFontDatabase.addApplicationFont(fpath)
                if font_id != -1:
                    loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return list(set(loaded_families))
