"""Testes de integridade do pacote: imports e assets."""

import importlib
import os

import pytest

from gafoam import resources

MODULOS_SEM_GUI = ["gafoam", "gafoam.foamdict", "gafoam.foamlint", "gafoam.logparse", "gafoam.resources"]

MODULOS_COM_GUI = [
    "gafoam.app",
    "gafoam.bc_editor",
    "gafoam.editor",
    "gafoam.filebrowser",
    "gafoam.handlers",
    "gafoam.main_window",
    "gafoam.menus",
    "gafoam.panels",
    "gafoam.report",
    "gafoam.residuals",
    "gafoam.stl_viewer",
    "gafoam.terminal",
]

# Ícones referenciados pela barra de ferramentas, abas e explorador de arquivos.
ICONES = [
    "open_case.svg", "run_allrun.svg", "stop_process.svg", "gear.svg", 
    "cmd_dollar.svg", "close_tab.svg", "gafoam_logo.svg", "folder.svg", 
    "file_dict.svg", "file_mesh.svg", "file_script.svg", "file_pdf.svg", 
    "file_foam.svg", "file_generic.svg"
]



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


def test_fontes_presentes_no_pacote():
    assert os.path.isfile(resources.font_path("FiraCode-Regular.ttf"))
    assert os.path.isfile(resources.font_path("FiraCode-Medium.ttf"))
    assert os.path.isfile(resources.font_path("FiraCode-Bold.ttf"))


def test_carregamento_de_fontes(qapp):
    familias = resources.load_application_fonts()
    assert any("Fira Code" in f for f in familias)
