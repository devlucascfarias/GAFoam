"""Configuração comum dos testes.

O Qt roda em modo offscreen para que os testes de interface não exijam
servidor gráfico.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CONTROL_DICT = """\
/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  11
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    object      controlDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     simpleFoam;

startFrom       startTime;

startTime       0;

stopAt          endTime;

endTime         500;

deltaT          0.001;

writeControl    timeStep;

writeInterval   100;   // grava a cada 100 passos

purgeWrite      0;

/* bloco de comentário
   com endTime 999; dentro, que deve ser ignorado */

runTimeModifiable true;

// ************************************************************************* //
"""

FV_SOLUTION = """\
FoamFile
{
    format      ascii;
    class       dictionary;
    object      fvSolution;
}

solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-06;
        relTol          0.1;
    }

    "(U|k|epsilon|omega)"
    {
        solver          smoothSolver;
        tolerance       1e-05;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;

    residualControl
    {
        p               1e-2;
        U               1e-3;
        "(k|epsilon|omega)" 1e-4;
    }
}

relaxationFactors
{
    equations
    {
        U               0.9;
    }
}
"""


@pytest.fixture
def case_dir(tmp_path):
    """Caso OpenFOAM mínimo, com controlDict e fvSolution preenchidos."""
    for sub in ("0", "constant", "system"):
        (tmp_path / sub).mkdir()
    (tmp_path / "system" / "controlDict").write_text(CONTROL_DICT, encoding="utf-8")
    (tmp_path / "system" / "fvSolution").write_text(FV_SOLUTION, encoding="utf-8")
    return tmp_path


@pytest.fixture(scope="session")
def qapp():
    """QApplication única para os testes que instanciam widgets."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance()
    if app is None:
        try:
            app = QtWidgets.QApplication([])
        except Exception as exc:  # pragma: no cover - depende do ambiente
            pytest.skip(f"Qt indisponível neste ambiente: {exc}")
    return app
