"""Testes do parsing de logs do solver."""

import math

import pytest

from gafoam import logparse

SIMPLE_LOG = """\
Time = 0.05

Courant Number mean: 0.0123 max: 0.4567
deltaT = 0.0001
smoothSolver:  Solving for Ux, Initial residual = 0.003, Final residual = 1e-08, No Iterations 3
smoothSolver:  Solving for Uy, Initial residual = 0.004, Final residual = 1e-08, No Iterations 3
smoothSolver:  Solving for Uz, Initial residual = 0.012, Final residual = 1e-08, No Iterations 3
GAMG:  Solving for p, Initial residual = 0.09, Final residual = 5e-07, No Iterations 12
ExecutionTime = 1.2 s
"""


def test_extrai_tempo_e_residuos():
    values, sim_time = logparse.parse_residuals(SIMPLE_LOG)

    assert sim_time == pytest.approx(0.05)
    assert values["p"] == pytest.approx(0.09)
    assert values["Co mean"] == pytest.approx(0.0123)
    assert values["Co max"] == pytest.approx(0.4567)
    assert values["deltaT"] == pytest.approx(0.0001)


def test_componentes_de_velocidade_viram_modulo():
    values, _ = logparse.parse_residuals(SIMPLE_LOG)

    esperado = math.sqrt(0.003**2 + 0.004**2 + 0.012**2)
    assert values["|U|"] == pytest.approx(esperado)
    for componente in ("Ux", "Uy", "Uz"):
        assert componente not in values


def test_caso_2d_usa_apenas_os_componentes_presentes():
    log = (
        "Solving for Ux, Initial residual = 0.3, Final residual = 1e-08\n"
        "Solving for Uy, Initial residual = 0.4, Final residual = 1e-08\n"
    )
    values, _ = logparse.parse_residuals(log)

    assert values["|U|"] == pytest.approx(0.5)


def test_ultimo_valor_de_cada_grandeza_prevalece():
    log = "Time = 1\nTime = 2\ndeltaT = 0.1\ndeltaT = 0.2\n"
    values, sim_time = logparse.parse_residuals(log)

    assert sim_time == pytest.approx(2.0)
    assert values["deltaT"] == pytest.approx(0.2)


def test_estatisticas_de_yplus_e_campos():
    log = (
        "y+ : min = 0.5, max = 120.0, average = 30.25\n"
        "    minMag() of U = 0.01\n"
        "    maxMag() of U = 12.5\n"
        "    min() of p = -3.5\n"
        "    max() of p = 7.25\n"
    )
    values, _ = logparse.parse_residuals(log)

    assert values["y+ min"] == pytest.approx(0.5)
    assert values["y+ max"] == pytest.approx(120.0)
    assert values["y+ avg"] == pytest.approx(30.25)
    assert values["U minMag"] == pytest.approx(0.01)
    assert values["U maxMag"] == pytest.approx(12.5)
    assert values["p min"] == pytest.approx(-3.5)
    assert values["p max"] == pytest.approx(7.25)


def test_function_object_de_vazao():
    log = "Time: 0.5 | Area: 0.0025 | Q: 1.5e-05 | U_mean: 0.006\n"
    values, _ = logparse.parse_residuals(log)

    assert values["Area"] == pytest.approx(0.0025)
    assert values["Q"] == pytest.approx(1.5e-05)
    assert values["U_mean"] == pytest.approx(0.006)


def test_texto_sem_dados_nao_produz_valores():
    values, sim_time = logparse.parse_residuals("Create mesh for time = 0\n")

    assert values == {}
    assert sim_time is None


def test_texto_vazio():
    assert logparse.parse_residuals("") == ({}, None)
