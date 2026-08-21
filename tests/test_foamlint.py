"""Testes do verificador sintático de dicionários."""

from gafoam import foamlint

CABECALHO = """\
/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  11
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""


def test_cabecalho_padrao_nao_gera_alerta():
    """O banner do OpenFOAM não é código e não deve exigir ponto e vírgula."""
    assert foamlint.check_syntax(CABECALHO) == []


def test_dicionario_valido():
    texto = CABECALHO + """
application     simpleFoam;

boundaryField
{
    inlet
    {
        type            fixedValue;
        value           uniform (0 0 0);
    }

    "(walls|frontAndBack)"
    {
        type            noSlip;
    }
}
"""
    assert foamlint.check_syntax(texto) == []


def test_listas_multilinha_nao_exigem_ponto_e_virgula():
    texto = CABECALHO + """
vertices
(
    (0 0 0)
    (1 0 0)
    (1 1 0)
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (20 20 1) simpleGrading (1 1 1)
);
"""
    assert foamlint.check_syntax(texto) == []


def test_campo_nonuniform_com_contagem_na_linha_seguinte():
    texto = CABECALHO + """
internalField   nonuniform List<scalar>
3
(
1.5
2.5
3.5
)
;
"""
    assert foamlint.check_syntax(texto) == []


def test_diretivas_e_macros_sao_ignoradas():
    texto = CABECALHO + """
#include "initialConditions"

internalField   $internalField;

functions
{
    #includeFunc residuals
}
"""
    assert foamlint.check_syntax(texto) == []


def test_codigo_cpp_embutido_e_ignorado():
    texto = CABECALHO + """
codeStream
{
    code
    #{
        const scalar x = 1.0;
        if (x > 0) { Info << x << endl; }
    #};
}
"""
    assert foamlint.check_syntax(texto) == []


def test_chaves_dentro_de_comentario_nao_desbalanceiam():
    texto = CABECALHO + """
/* exemplo desativado
solvers
{
*/

application     simpleFoam;
"""
    assert foamlint.check_syntax(texto) == []


def test_detecta_chave_nao_fechada():
    texto = CABECALHO + """
solvers
{
    p
    {
        solver          GAMG;
    }
"""
    erros = foamlint.check_syntax(texto)

    assert len(erros) == 1
    assert "nunca foi fechado" in erros[0]


def test_detecta_fechamento_inesperado():
    erros = foamlint.check_syntax("solvers\n{\n}\n}\n")

    assert len(erros) == 1
    assert "inesperado" in erros[0]
    assert "linha 4" in erros[0]


def test_detecta_delimitador_trocado():
    erros = foamlint.check_syntax("valores\n(\n    1 2 3\n}\n")

    assert len(erros) == 1
    assert "incorreto" in erros[0]


def test_detecta_ponto_e_virgula_ausente():
    texto = CABECALHO + """
application     simpleFoam

startTime       0;
"""
    erros = foamlint.check_syntax(texto)

    assert len(erros) == 1
    assert "ponto e vírgula" in erros[0]


def test_subdicionario_nao_e_falso_positivo():
    texto = CABECALHO + """
boundaryField
{
    movingWall
    {
        type            noSlip;
    }
}
"""
    assert foamlint.check_syntax(texto) == []


def test_comentario_de_linha_apos_entrada():
    texto = CABECALHO + "\nwriteInterval   100;   // a cada 100 passos\n"

    assert foamlint.check_syntax(texto) == []


def test_ponto_e_virgula_faltando_dentro_de_subdicionario():
    texto = CABECALHO + """
solvers
{
    p
    {
        solver          GAMG
        tolerance       1e-06;
    }
}
"""
    erros = foamlint.check_syntax(texto)

    assert len(erros) == 1
    assert "ponto e vírgula" in erros[0]


def test_texto_vazio():
    assert foamlint.check_syntax("") == []


def test_arquivo_log_nao_gera_alerta():
    log_text = """/*---------------------------------------------------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Website:  https://openfoam.org                  |
|   \\\\  /    A nd           | Version:  12                                    |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
Build : 12-86e126a7bc4d
Exec : foamRun -parallel
Date : Jul 31 2026
Time : 13:38:26
Host : "reynolds-02"
PID : 637649
"""
    assert foamlint.check_syntax(log_text, "log.foamRun") == []
    assert foamlint.is_openfoam_dict("log.foamRun", log_text) is False
    assert foamlint.is_openfoam_dict("Allrun", "#!/bin/sh\n./Allclean") is False
