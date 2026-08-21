"""Testes de interface, executados com o Qt em modo offscreen.

O painel 3D é substituído por um substituto leve: o `QtInteractor` do
pyvistaqt exige um servidor X real e derruba o processo em ambientes
headless. O que se testa aqui é a lógica da janela, não a renderização.
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QWidget  # noqa: E402


class _ViewerStub:
    def __init__(self):
        self.loaded = []

    def load_meshes(self, files_list):
        self.loaded.extend(files_list)


class _GeometryStub(QWidget):
    """Substituto de `CaseGeometryWidget` sem dependência de VTK."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewer = _ViewerStub()
        self.scanned = []
        self.selected = []
        self.available = set()

    def scan_case(self, case_path):
        self.scanned.append(case_path)

    def select_mesh(self, file_path):
        self.selected.append(file_path)
        return file_path in self.available


@pytest.fixture
def window(qapp, monkeypatch):
    """Janela principal com o painel de geometria substituído."""
    from gafoam import main_window as mw

    monkeypatch.setattr(mw, "CaseGeometryWidget", _GeometryStub)
    win = mw.MainWindow()
    yield win
    win.close()


def _titulos(tab_widget):
    return [tab_widget.tabText(i) for i in range(tab_widget.count())]


def test_janela_monta_paineis_principais(window):
    assert "Console" in _titulos(window.tab_widget)
    assert "Simulation" in _titulos(window.tab_widget)
    assert "Boundary Conditions" in _titulos(window.tab_widget)
    assert window.control_dock is not None
    assert window.fv_schemes_dock is not None
    assert window.fv_solution_dock is not None
    assert window.toolbar is not None



def test_grafico_de_residuos_comeca_oculto(window):
    assert not window.residuals_view.isVisible()


def test_geometria_nao_ocupa_o_editor_por_padrao(window):
    """O painel 3D só deve existir depois que uma malha for aberta."""
    assert "Geometry" not in _titulos(window.editor_tabs)
    assert window.editor_tabs.indexOf(window.geom_view) == -1
    assert window.geom_view.scanned == []


def test_abrir_malha_cria_a_aba_de_geometria(window):
    window.show_geometry("/tmp/peca.stl")

    assert "Geometry" in _titulos(window.editor_tabs)
    assert window.editor_tabs.currentWidget() is window.geom_view


def test_malha_fora_da_varredura_e_carregada_avulsa(window):
    window.show_geometry("/tmp/peca.stl")

    assert window.geom_view.viewer.loaded == [("peca.stl", "/tmp/peca.stl")]


def test_malha_conhecida_e_apenas_selecionada(window):
    window.geom_view.available.add("/tmp/peca.stl")

    window.show_geometry("/tmp/peca.stl")

    assert window.geom_view.selected == ["/tmp/peca.stl"]
    assert window.geom_view.viewer.loaded == []


def test_reabrir_geometria_reaproveita_a_mesma_aba(window):
    window.show_geometry("/tmp/a.stl")
    window.show_geometry("/tmp/b.stl")

    assert _titulos(window.editor_tabs).count("Geometry") == 1


def test_caso_e_varrido_uma_unica_vez(window, case_dir):
    window.current_case = str(case_dir)

    window.show_geometry("/tmp/a.stl")
    window.show_geometry("/tmp/b.stl")

    assert window.geom_view.scanned == [str(case_dir)]


def test_aba_de_geometria_e_permanente(window):
    window.show_geometry("/tmp/a.stl")
    index = window.editor_tabs.indexOf(window.geom_view)

    window.on_tab_close_requested(index)

    # Permanece aberta pois é permanente
    assert "Geometry" in _titulos(window.editor_tabs)



def test_arquivo_de_malha_nao_abre_no_editor(window, tmp_path):
    stl = tmp_path / "peca.stl"
    stl.write_text("solid vazio\nendsolid vazio\n", encoding="utf-8")

    index = window.file_browser.file_model.index(str(stl))
    window.file_browser.file_model.setRootPath(str(tmp_path))
    if index.isValid():
        window.on_file_clicked(index)
        assert str(stl) not in window.path_to_editor
        assert window.editor_tabs.currentWidget() is window.geom_view


def test_editor_abre_arquivo_de_texto_em_nova_aba(window):
    window.open_file_in_tab("/tmp/controlDict", "application simpleFoam;\n")

    assert "controlDict" in _titulos(window.editor_tabs)
    assert window.current_editor() is not None


def test_linter_do_editor_usa_o_verificador_do_pacote(qapp):
    from gafoam.editor import EditorContainerWidget

    container = EditorContainerWidget()

    assert container.check_syntax("application simpleFoam;\n") == []
    assert container.check_syntax("solvers\n{\n") != []


def test_monitor_de_convergencia_marca_valores(qapp, case_dir):
    from gafoam.panels import ConvergenceMonitorWidget

    monitor = ConvergenceMonitorWidget()
    monitor.load_case(str(case_dir))

    monitor.update_residual("p", 1e-3)
    monitor.update_residual("U", 1e-2)

    assert monitor.table.columnCount() == 3
    assert monitor.table.rowCount() == 2
    assert monitor.table.item(0, 0).text() == "p"
    assert "Converged" in monitor.table.item(0, 2).text()
    assert monitor.table.item(1, 0).text() == "U"
    assert "Iterating" in monitor.table.item(1, 2).text()


def test_dock_do_control_dict_carrega_parametros(qapp, case_dir):
    from gafoam.panels import ControlDictDockWidget

    dock = ControlDictDockWidget()
    dock.load_case(str(case_dir))

    assert dock.isEnabled()
    assert dock.txt_app.text() == "simpleFoam"
    assert dock.spin_endtime.value() == pytest.approx(500.0)
    assert dock.spin_deltat.value() == pytest.approx(0.001)
    assert dock.spin_interval.value() == pytest.approx(100.0)


def test_dock_desabilita_sem_caso(qapp, tmp_path):
    from gafoam.panels import ControlDictDockWidget

    dock = ControlDictDockWidget()
    dock.load_case(str(tmp_path))

    assert not dock.isEnabled()


def test_qualidade_da_geometria_stl(tmp_path):
    from gafoam.stl_viewer import check_mesh_quality
    import pyvista as pv

    # Cria uma esfera fechada (watertight)
    sphere = pv.Sphere()
    diag = check_mesh_quality(sphere)

    assert diag is not None
    assert diag["is_watertight"] is True
    assert diag["open_edges"] == 0
    assert diag["area"] > 0
    assert diag["volume"] > 0


def test_deteccao_de_patches_stl(tmp_path):
    from gafoam.stl_viewer import detect_stl_patches

    stl_file = tmp_path / "multisolid.stl"
    stl_file.write_text(
        "solid wing\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 1 1 0\nendloop\nendfacet\nendsolid wing\n"
        "solid fuselage\nfacet normal 0 1 0\nouter loop\nvertex 0 0 0\nvertex 0 1 0\nvertex 0 1 1\nendloop\nendfacet\nendsolid fuselage\n",
        encoding="utf-8"
    )

    patches = detect_stl_patches(str(stl_file))
    assert len(patches) == 2
    assert patches[0]["name"] == "wing"
    assert patches[0]["faces"] == 1
    assert patches[1]["name"] == "fuselage"
    assert patches[1]["faces"] == 1


def test_recarregamento_arquivo_externo(window, tmp_path):
    file_path = tmp_path / "system" / "controlDict"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("application simpleFoam;", encoding="utf-8")

    window.open_file_in_tab(str(file_path), "application simpleFoam;")
    editor = window.path_to_editor[str(file_path)]
    assert editor.toPlainText() == "application simpleFoam;"

    # Modifica o arquivo externamente
    file_path.write_text("application pimpleFoam;\nendTime 100;", encoding="utf-8")
    window._on_external_file_changed(str(file_path))

    assert editor.toPlainText() == "application pimpleFoam;\nendTime 100;"


def test_arquivo_excluido_externamente(window, tmp_path):
    file_path = tmp_path / "system" / "fvSchemes"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("ddtSchemes default Euler;", encoding="utf-8")

    window.open_file_in_tab(str(file_path), "ddtSchemes default Euler;")
    assert str(file_path) in window.path_to_editor

    # Exclui o arquivo no disco
    file_path.unlink()
    window._on_external_file_changed(str(file_path))

    idx = window.editor_tabs.indexOf(window.path_to_editor[str(file_path)].parentWidget())
    assert "[excluído]" in window.editor_tabs.tabText(idx)


def test_clique_pasta_alterna_expansao(qapp, tmp_path):
    from gafoam.filebrowser import FileBrowser

    sub_dir = tmp_path / "subfolder"
    sub_dir.mkdir()

    browser = FileBrowser(parent=None)
    browser.set_root(str(tmp_path))

    idx = browser.file_model.index(str(sub_dir))
    assert browser.file_model.isDir(idx)
    assert not browser.file_view.isExpanded(idx)

    # Simula clique na pasta
    browser._on_tree_clicked(idx)
    assert browser.file_view.isExpanded(idx)

    # Segundo clique recolhe
    browser._on_tree_clicked(idx)
    assert not browser.file_view.isExpanded(idx)


