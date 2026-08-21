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


def test_verify_case_complete(case_dir):
    (case_dir / "system" / "fvSchemes").write_text("/* fvSchemes */", encoding="utf-8")
    poly_mesh = case_dir / "constant" / "polyMesh"
    poly_mesh.mkdir(parents=True, exist_ok=True)
    (poly_mesh / "points").write_text("/* points */", encoding="utf-8")

    is_valid, issues, warnings = foamdict.verify_case(str(case_dir))
    assert is_valid is True
    assert issues == []


def test_verify_case_missing_mesh(case_dir):
    (case_dir / "system" / "fvSchemes").write_text("/* fvSchemes */", encoding="utf-8")
    # Não cria polyMesh
    is_valid, issues, warnings = foamdict.verify_case(str(case_dir))
    assert is_valid is False
    assert any("Mesh not found" in i for i in issues)


def test_list_field_files(case_dir):
    (case_dir / "0" / "p").write_text("/* p */", encoding="utf-8")
    (case_dir / "0" / "U").write_text("/* U */", encoding="utf-8")
    (case_dir / "0" / "uniform").mkdir() # directory should be ignored
    fields = foamdict.list_field_files(str(case_dir))
    assert "p" in fields
    assert "U" in fields
    assert "uniform" not in fields



def test_boundary_field_read_and_write(tmp_path):
    p_content = """/* OpenFOAM */
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      p;
}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;

boundaryField
{
    inlet
    {
        type            zeroGradient;
    }
    outlet
    {
        type            fixedValue;
        value           uniform 0;
    }
}
"""
    p_file = tmp_path / "p"
    p_file.write_text(p_content, encoding="utf-8")

    bcs = foamdict.read_boundary_field(str(p_file))
    assert "inlet" in bcs
    assert bcs["inlet"]["type"] == "zeroGradient"
    assert "outlet" in bcs
    assert bcs["outlet"]["type"] == "fixedValue"
    assert bcs["outlet"]["value"] == "uniform 0"

    # Modifica e escreve de volta
    bcs["inlet"]["type"] = "fixedValue"
    bcs["inlet"]["value"] = "uniform 10"
    assert foamdict.write_boundary_field(str(p_file), bcs)

    # Re-lê
    bcs_new = foamdict.read_boundary_field(str(p_file))
    assert bcs_new["inlet"]["type"] == "fixedValue"
    assert bcs_new["inlet"]["value"] == "uniform 10"


def test_fv_schemes_read_and_write(tmp_path):
    sys_dir = tmp_path / "system"
    sys_dir.mkdir(parents=True, exist_ok=True)
    schemes_content = """/* fvSchemes */
ddtSchemes
{
    default         Euler;
}
gradSchemes
{
    default         Gauss linear;
}
divSchemes
{
    default         none;
}
laplacianSchemes
{
    default         Gauss linear corrected;
}
"""
    (sys_dir / "fvSchemes").write_text(schemes_content, encoding="utf-8")

    schemes = foamdict.read_fv_schemes(str(tmp_path))
    assert schemes["ddtSchemes"] == "Euler"
    assert schemes["gradSchemes"] == "Gauss linear"

    assert foamdict.write_fv_schemes(str(tmp_path), {"ddtSchemes": "backward"})
    schemes_new = foamdict.read_fv_schemes(str(tmp_path))
    assert schemes_new["ddtSchemes"] == "backward"


def test_fv_solution_read_and_write(tmp_path):
    sys_dir = tmp_path / "system"
    sys_dir.mkdir(parents=True, exist_ok=True)
    sol_content = """/* fvSolution */
PIMPLE
{
    nCorrectors              2;
    nNonOrthogonalCorrectors 1;
}
relaxationFactors
{
    fields
    {
        p               0.3;
    }
    equations
    {
        U               0.7;
    }
}
"""
    (sys_dir / "fvSolution").write_text(sol_content, encoding="utf-8")

    sol = foamdict.read_fv_solution(str(tmp_path))
    assert sol["algorithm"] == "PIMPLE"
    assert sol["algorithm_params"]["nCorrectors"] == "2"
    assert sol["relaxation_fields"]["p"] == pytest.approx(0.3)
    assert sol["relaxation_equations"]["U"] == pytest.approx(0.7)

    assert foamdict.write_fv_solution_params(
        str(tmp_path),
        algorithm_params={"nCorrectors": "3"},
        relaxation_fields={"p": 0.4},
    )

    sol_new = foamdict.read_fv_solution(str(tmp_path))
    assert sol_new["algorithm_params"]["nCorrectors"] == "3"
    assert sol_new["relaxation_fields"]["p"] == pytest.approx(0.4)


def test_decompose_par_dict_read_and_write(tmp_path):
    # Cria template automático
    assert foamdict.write_decompose_par_dict(
        str(tmp_path),
        {"numberOfSubdomains": "8", "method": "scotch"}
    )

    data = foamdict.read_decompose_par_dict(str(tmp_path))
    assert data["numberOfSubdomains"] == "8"
    assert data["method"] == "scotch"

    # Atualiza
    assert foamdict.write_decompose_par_dict(
        str(tmp_path),
        {"numberOfSubdomains": "16", "method": "hierarchical"}
    )
    data_up = foamdict.read_decompose_par_dict(str(tmp_path))
    assert data_up["numberOfSubdomains"] == "16"
    assert data_up["method"] == "hierarchical"


def test_turbulence_properties_read_and_write(tmp_path):
    assert foamdict.write_turbulence_properties(
        str(tmp_path),
        {"simulationType": "RAS", "model": "kOmegaSST", "turbulence": "on"}
    )

    data = foamdict.read_turbulence_properties(str(tmp_path))
    assert data["simulationType"] == "RAS"
    assert data["model"] == "kOmegaSST"
    assert data["turbulence"] == "on"

    assert foamdict.write_turbulence_properties(
        str(tmp_path),
        {"simulationType": "LES", "model": "WALE", "turbulence": "off"}
    )
    data_up = foamdict.read_turbulence_properties(str(tmp_path))
    assert data_up["simulationType"] == "LES"
    assert data_up["model"] == "WALE"
    assert data_up["turbulence"] == "off"


def test_transport_properties_read_and_write(tmp_path):
    assert foamdict.write_transport_properties(
        str(tmp_path),
        {"nu": "1.004e-06", "rho": "998.2"}
    )

    data = foamdict.read_transport_properties(str(tmp_path))
    assert float(data["nu"]) == pytest.approx(1.004e-06)
    assert float(data["rho"]) == pytest.approx(998.2)

    assert foamdict.write_transport_properties(
        str(tmp_path),
        {"nu": "1.5e-05", "rho": "1.2"}
    )
    data_up = foamdict.read_transport_properties(str(tmp_path))
    assert float(data_up["nu"]) == pytest.approx(1.5e-05)
    assert float(data_up["rho"]) == pytest.approx(1.2)


