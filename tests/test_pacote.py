"""Testes de integridade do pacote: imports e assets."""

import importlib
import os

import pytest

from gafoam import resources

MODULOS_SEM_GUI = ["gafoam", "gafoam.foamdict", "gafoam.foamlint", "gafoam.logparse", "gafoam.resources"]

MODULOS_COM_GUI = [
    "gafoam.app",
    "gafoam.editor",
    "gafoam.filebrowser",
    "gafoam.handlers",
    "gafoam.main_window",
    "gafoam.menus",
    "gafoam.panels",
    "gafoam.residuals",
    "gafoam.stl_viewer",
    "gafoam.terminal",
]

# Ícones referenciados pela barra de ferramentas.
ICONES = ["open_case.svg", "run_allrun.svg", "stop_process.svg", "gear.svg"]


@pytest.mark.parametrize("nome", MODULOS_SEM_GUI)
def test_importa_modulo_sem_gui(nome):
    assert importlib.import_module(nome) is not None


@pytest.mark.parametrize("nome", MODULOS_COM_GUI)
def test_importa_modulo_com_gui(nome, qapp):
    assert importlib.import_module(nome) is not None


@pytest.mark.parametrize("icone", ICONES)
def test_icone_presente_no_pacote(icone):
    assert resources.has_icon(icone), f"{icone} ausente em {resources.ICONS_DIR}"


def test_icon_path_dentro_do_pacote():
    caminho = resources.icon_path("open_case.svg")

    assert os.path.isabs(caminho)
    assert caminho.endswith(os.path.join("gafoam", "icons", "open_case.svg"))
