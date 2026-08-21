"""Extração de grandezas dos logs do OpenFOAM.

Módulo sem dependência de Qt: recebe texto ou caminhos e devolve dados,
para que a lógica de parsing possa ser exercitada sem instanciar a interface.
"""

import glob
import math
import os
import re
from collections import namedtuple


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


def parse_all_time_steps(text):
    """Analisa o texto dividindo por passos de tempo (Time = ... ou Time:...).
    
    Retorna uma lista de tuplas `(valores, sim_time)` para cada passo de tempo encontrado.
    """
    if not text:
        return []

    matches = list(RE_TIME.finditer(text))
    if len(matches) <= 1:
        vals, sim_time = parse_residuals(text)
        return [(vals, sim_time)] if vals else []

    steps = []
    for i, match in enumerate(matches):
        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start_idx:end_idx]
        vals, sim_time = parse_residuals(block)
        if sim_time is None:
            try:
                sim_time = float(match.group(1))
            except ValueError:
                pass
        if vals and sim_time is not None:
            steps.append((vals, sim_time))

    return steps


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


# ---------------------------------------------------------------------------
# Divergence detection (Feature 5)
# ---------------------------------------------------------------------------

RE_NAN = re.compile(r"\b[Nn][Aa][Nn]\b")
RE_FLOATING_POINT_EXCEPTION = re.compile(r"#0\s+Foam::error::printStack|Floating point exception")

DivergenceAlert = namedtuple("DivergenceAlert", ["type", "variable", "message"])

# Residual spike threshold: if a residual jumps by this factor, it's a spike.
_SPIKE_FACTOR = 100.0


def detect_divergence(current_values, previous_values=None, co_limit=10.0):
    """Analyse current residuals for signs of numerical divergence.

    Parameters
    ----------
    current_values : dict
        Mapping of variable name to its current residual value.
    previous_values : dict or None
        Mapping of variable name to its previous residual value.
    co_limit : float
        Courant number threshold above which a warning is issued.

    Returns
    -------
    list[DivergenceAlert]
        List of alerts detected.  Empty list means no issues.
    """
    alerts = []

    for name, val in current_values.items():
        # NaN detection
        val_str = str(val)
        if RE_NAN.search(val_str):
            alerts.append(DivergenceAlert(
                type="nan",
                variable=name,
                message=f"NaN detected in '{name}'! Simulation is likely diverging.",
            ))
            continue

        try:
            fval = float(val)
        except (ValueError, TypeError):
            continue

        # Courant number exceeded
        if ("co" in name.lower() or "courant" in name.lower()) and fval > co_limit:
            alerts.append(DivergenceAlert(
                type="courant_exceeded",
                variable=name,
                message=f"Courant number {name} = {fval:.2f} exceeds limit ({co_limit}).",
            ))

        # Residual spike detection
        if previous_values and name in previous_values:
            try:
                prev = float(previous_values[name])
            except (ValueError, TypeError):
                continue
            if prev > 0 and fval / prev >= _SPIKE_FACTOR:
                alerts.append(DivergenceAlert(
                    type="residual_spike",
                    variable=name,
                    message=f"Residual spike in '{name}': {prev:.2e} -> {fval:.2e} ({fval/prev:.0f}x increase).",
                ))

    return alerts


def detect_divergence_in_text(text):
    """Scan raw log text for fatal divergence markers.

    Returns a list of ``DivergenceAlert`` for NaN tokens or floating-point
    exception stack traces found in the text.
    """
    alerts = []
    if RE_NAN.search(text):
        alerts.append(DivergenceAlert(
            type="nan",
            variable="(log output)",
            message="NaN value detected in solver output.",
        ))
    if RE_FLOATING_POINT_EXCEPTION.search(text):
        alerts.append(DivergenceAlert(
            type="floating_point_exception",
            variable="(solver)",
            message="Floating point exception detected — solver crashed.",
        ))
    return alerts
