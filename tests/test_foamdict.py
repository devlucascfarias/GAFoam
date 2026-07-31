"""Testes de leitura e escrita dos dicionários do caso."""

import pytest

from gafoam import foamdict


def test_validacao_de_caso_completo(case_dir):
    assert foamdict.validate_case_dirs(str(case_dir)) == []
    assert foamdict.is_valid_case(str(case_dir))


def test_validacao_aponta_diretorios_ausentes(tmp_path):
    (tmp_path / "system").mkdir()

    faltando = foamdict.validate_case_dirs(str(tmp_path))

    assert faltando == ["0", "constant"]
    assert not foamdict.is_valid_case(str(tmp_path))


def test_caminho_vazio_falta_tudo():
    assert foamdict.validate_case_dirs("") == ["0", "constant", "system"]


def test_leitura_do_control_dict(case_dir):
    params = foamdict.read_control_dict(str(case_dir))

    assert params["application"] == "simpleFoam"
    assert params["endTime"] == "500"
    assert params["deltaT"] == "0.001"
    assert params["writeInterval"] == "100"


def test_comentarios_nao_interferem_na_leitura(case_dir):
    # O bloco /* ... */ do controlDict contém "endTime 999;" e não pode vencer.
    assert foamdict.read_control_dict(str(case_dir))["endTime"] == "500"


def test_caso_sem_control_dict(tmp_path):
    assert foamdict.read_control_dict(str(tmp_path)) == {}
    assert foamdict.write_control_dict(str(tmp_path), {"endTime": "1"}) is False


def test_escrita_preserva_o_restante_do_arquivo(case_dir):
    original = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")

    assert foamdict.write_control_dict(
        str(case_dir), {"endTime": "750", "deltaT": "0.002", "writeInterval": "50"}
    )

    params = foamdict.read_control_dict(str(case_dir))
    assert params["endTime"] == "750"
    assert params["deltaT"] == "0.002"
    assert params["writeInterval"] == "50"
    assert params["application"] == "simpleFoam"

    novo = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    assert "FoamFile" in novo
    assert "purgeWrite      0;" in novo
    assert "runTimeModifiable true;" in novo
    assert len(novo.splitlines()) == len(original.splitlines())


def test_residual_control(case_dir):
    targets = foamdict.parse_residual_controls(str(case_dir))

    assert targets["p"] == pytest.approx(1e-2)
    assert targets["U"] == pytest.approx(1e-3)
    assert targets["(k|epsilon|omega)"] == pytest.approx(1e-4)
    # Entradas de outros blocos não podem vazar para o resultado.
    assert "nNonOrthogonalCorrectors" not in targets
    assert "relTol" not in targets


def test_residual_control_ausente(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "fvSolution").write_text("solvers\n{\n}\n", encoding="utf-8")

    assert foamdict.parse_residual_controls(str(tmp_path)) == {}


def test_alvo_por_expressao_regular():
    targets = {"p": 1e-2, "(k|epsilon|omega)": 1e-4}

    assert foamdict.match_residual_target(targets, "p") == pytest.approx(1e-2)
    assert foamdict.match_residual_target(targets, "epsilon") == pytest.approx(1e-4)
    assert foamdict.match_residual_target(targets, "nuTilda") == pytest.approx(1e-5)
    assert foamdict.match_residual_target({}, "p", default=1e-7) == pytest.approx(1e-7)


def test_expressao_casa_o_nome_inteiro():
    """A chave 'p' não pode capturar 'epsilon' nem 'p_rgh'."""
    targets = {"p": 1e-2}

    assert foamdict.match_residual_target(targets, "epsilon") == pytest.approx(1e-5)
    assert foamdict.match_residual_target(targets, "p_rgh") == pytest.approx(1e-5)


def test_chave_literal_tem_precedencia_sobre_regex():
    targets = {".*": 1e-3, "U": 1e-6}

    assert foamdict.match_residual_target(targets, "U") == pytest.approx(1e-6)


def test_expressao_invalida_nao_quebra_a_busca():
    targets = {"U(": 1e-3, "p": 1e-2}

    assert foamdict.match_residual_target(targets, "p") == pytest.approx(1e-2)
    assert foamdict.match_residual_target(targets, "U(") == pytest.approx(1e-3)
