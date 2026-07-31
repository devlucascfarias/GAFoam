"""Extração de grandezas dos logs do OpenFOAM.

Módulo sem dependência de Qt: recebe texto ou caminhos e devolve dados,
para que a lógica de parsing possa ser exercitada sem instanciar a interface.
"""

import glob
import math
import os
import re

RE_TIME = re.compile(r"\bTime\s*[=:]\s*([\d.eE+-]+)")
RE_RESIDUAL = re.compile(r"Solving for (\w+), Initial residual = ([\d.eE+-]+)")
RE_YPLUS = re.compile(
    r"y\+\s*:\s*min\s*=\s*([\d.eE+-]+),\s*max\s*=\s*([\d.eE+-]+),\s*average\s*=\s*([\d.eE+-]+)"
)
RE_COURANT = re.compile(r"Courant Number mean:\s*([\d.eE+-]+)\s*max:\s*([\d.eE+-]+)")
RE_DELTAT = re.compile(r"deltaT\s*=\s*([\d.eE+-]+)")
RE_FLOW = re.compile(
    r"Time:[^|\n]*\|\s*Area:\s*([\d.eE+-]+)\s*\|\s*Q:\s*([\d.eE+-]+)\s*\|\s*U_mean:\s*([\d.eE+-]+)"
)
RE_U_MINMAG = re.compile(r"minMag\(\)\s+of\s+U\s*=\s*([\d.eE+-]+)")
RE_U_MAXMAG = re.compile(r"maxMag\(\)\s+of\s+U\s*=\s*([\d.eE+-]+)")
RE_P_MIN = re.compile(r"min\(\)\s+of\s+p\s*=\s*([\d.eE+-]+)")
RE_P_MAX = re.compile(r"max\(\)\s+of\s+p\s*=\s*([\d.eE+-]+)")

# Componentes de velocidade colapsados em uma única curva |U|.
U_COMPONENTS = ("Ux", "Uy", "Uz")


def _last_float(pattern, text):
    """Último valor capturado pelo padrão, ou None se não houver ocorrência válida."""
    value = None
    for m in pattern.finditer(text):
        try:
            value = float(m.group(1))
        except ValueError:
            pass
    return value


def parse_residuals(text):
    """Analisa um trecho de log do solver.

    Retorna `(valores, tempo)`, onde `valores` mapeia nome da grandeza para o
    último valor observado no trecho e `tempo` é o último `Time =` encontrado
    (None se o trecho não contiver nenhum).
    """
    values = {}

    sim_time = _last_float(RE_TIME, text)

    for m in RE_RESIDUAL.finditer(text):
        try:
            values[m.group(1)] = float(m.group(2))
        except ValueError:
            pass

    # Módulo da velocidade a partir dos componentes disponíveis (2D ou 3D).
    present = [k for k in U_COMPONENTS if k in values]
    if present:
        umag = math.sqrt(sum(values[k] ** 2 for k in present))
        for k in U_COMPONENTS:
            values.pop(k, None)
        values["|U|"] = umag

    for m in RE_YPLUS.finditer(text):
        try:
            values["y+ min"] = float(m.group(1))
            values["y+ max"] = float(m.group(2))
            values["y+ avg"] = float(m.group(3))
        except ValueError:
            pass

    for m in RE_COURANT.finditer(text):
        try:
            values["Co mean"] = float(m.group(1))
            values["Co max"] = float(m.group(2))
        except ValueError:
            pass

    deltat = _last_float(RE_DELTAT, text)
    if deltat is not None:
        values["deltaT"] = deltat

    for m in RE_FLOW.finditer(text):
        try:
            values["Area"] = float(m.group(1))
            values["Q"] = float(m.group(2))
            values["U_mean"] = float(m.group(3))
        except ValueError:
            pass

    for key, pattern in (
        ("U minMag", RE_U_MINMAG),
        ("U maxMag", RE_U_MAXMAG),
        ("p min", RE_P_MIN),
        ("p max", RE_P_MAX),
    ):
        value = _last_float(pattern, text)
        if value is not None:
            values[key] = value

    return values, sim_time


def choose_solver_log_file(case_path):
    """Log do solver a acompanhar no caso.

    Prefere `log.foam`; na ausência dele, o `log.*` modificado mais
    recentemente, ignorando arquivos terminados em `.log`.
    """
    if not case_path:
        return None

    preferred = os.path.join(case_path, "log.foam")
    if os.path.isfile(preferred):
        return preferred

    candidates = [
        p
        for p in glob.glob(os.path.join(case_path, "log.*"))
        if os.path.isfile(p) and not p.endswith(".log")
    ]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)
