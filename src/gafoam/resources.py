"""Localização dos assets empacotados junto ao código."""

import os

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def icon_path(filename):
    """Caminho absoluto de um ícone do pacote (o arquivo pode não existir)."""
    return os.path.join(ICONS_DIR, filename)


def has_icon(filename):
    """Indica se o ícone está presente no pacote."""
    return os.path.isfile(icon_path(filename))
