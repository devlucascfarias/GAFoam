"""Testes da escolha do log do solver a acompanhar."""

import os

from gafoam import logparse


def _write(path, mtime):
    path.write_text("dados\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_log_foam_tem_prioridade(tmp_path):
    _write(tmp_path / "log.foam", 1000)
    _write(tmp_path / "log.simpleFoam", 2000)

    assert logparse.choose_solver_log_file(str(tmp_path)) == str(tmp_path / "log.foam")


def test_sem_log_foam_usa_o_mais_recente(tmp_path):
    _write(tmp_path / "log.blockMesh", 1000)
    _write(tmp_path / "log.simpleFoam", 3000)
    _write(tmp_path / "log.decomposePar", 2000)

    escolhido = logparse.choose_solver_log_file(str(tmp_path))

    assert escolhido == str(tmp_path / "log.simpleFoam")


def test_arquivos_terminados_em_log_sao_ignorados(tmp_path):
    _write(tmp_path / "log.antigo", 1000)
    _write(tmp_path / "log.saida.log", 5000)

    assert logparse.choose_solver_log_file(str(tmp_path)) == str(tmp_path / "log.antigo")


def test_diretorio_sem_logs(tmp_path):
    assert logparse.choose_solver_log_file(str(tmp_path)) is None


def test_caminho_vazio():
    assert logparse.choose_solver_log_file(None) is None
    assert logparse.choose_solver_log_file("") is None
