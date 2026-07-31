"""Leitura e escrita dos dicionários de um caso OpenFOAM.

Módulo sem dependência de Qt, para que a manipulação dos arquivos do caso
possa ser testada isoladamente da interface.
"""

import os
import re

# Subdiretórios obrigatórios de um caso OpenFOAM.
REQUIRED_CASE_DIRS = ("0", "constant", "system")

# Chaves do controlDict expostas na interface.
CONTROL_DICT_KEYS = ("endTime", "deltaT", "writeInterval", "application")

RE_LINE_COMMENT = re.compile(r"//.*")
RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
RE_RESIDUAL_CONTROL = re.compile(r"residualControl\s*\{")
RE_DICT_ENTRY = re.compile(r'([a-zA-Z0-9_"\(\)\|\s\-]+)\s+([0-9eE\.\-]+)\s*;')


def validate_case_dirs(path):
    """Subdiretórios obrigatórios ausentes no caminho informado."""
    if not path:
        return list(REQUIRED_CASE_DIRS)
    return [d for d in REQUIRED_CASE_DIRS if not os.path.isdir(os.path.join(path, d))]


def is_valid_case(path):
    """Indica se o caminho tem a estrutura mínima de um caso OpenFOAM."""
    return not validate_case_dirs(path)


def control_dict_path(case_path):
    return os.path.join(case_path, "system", "controlDict")


def fv_solution_path(case_path):
    return os.path.join(case_path, "system", "fvSolution")


def strip_comments(content):
    """Remove comentários de linha e de bloco de um dicionário."""
    return RE_BLOCK_COMMENT.sub("", RE_LINE_COMMENT.sub("", content))


def read_control_dict(case_path):
    """Valores de `CONTROL_DICT_KEYS` no controlDict do caso.

    Devolve um dicionário vazio se o arquivo não existir ou não puder ser lido.
    """
    dict_path = control_dict_path(case_path)
    if not os.path.isfile(dict_path):
        return {}
    try:
        with open(dict_path, "r", encoding="utf-8") as f:
            clean = strip_comments(f.read())
    except OSError:
        return {}

    values = {}
    for key in CONTROL_DICT_KEYS:
        m = re.search(rf"\b{key}\s+([^;]+);", clean)
        if m:
            values[key] = m.group(1).strip()
    return values


def write_control_dict(case_path, values):
    """Atualiza as chaves informadas no controlDict preservando o resto do arquivo.

    Retorna True em caso de sucesso.
    """
    dict_path = control_dict_path(case_path)
    if not os.path.isfile(dict_path):
        return False
    try:
        with open(dict_path, "r", encoding="utf-8") as f:
            content = f.read()

        for key, val in values.items():
            pattern = rf"(\b{key}\s+)[^;]+(\s*;)"
            content = re.sub(pattern, rf"\g<1>{val}\g<2>", content)

        with open(dict_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except OSError:
        return False


def parse_residual_controls(case_path):
    """Tolerâncias declaradas no bloco `residualControl` do fvSolution.

    As chaves são mantidas como escritas no arquivo (podem ser expressões
    regulares, como `"(U|k|epsilon)"`, conforme a convenção do OpenFOAM).
    """
    sol_path = fv_solution_path(case_path)
    if not os.path.isfile(sol_path):
        return {}
    try:
        with open(sol_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return {}

    block = _extract_braced_block(content, RE_RESIDUAL_CONTROL)
    if block is None:
        return {}

    targets = {}
    for m in RE_DICT_ENTRY.finditer(block):
        key = m.group(1).strip().strip('"').strip("'")
        try:
            targets[key] = float(m.group(2))
        except ValueError:
            pass
    return targets


def _extract_braced_block(content, header_pattern):
    """Conteúdo entre as chaves que seguem `header_pattern`, respeitando aninhamento."""
    match = header_pattern.search(content)
    if not match:
        return None

    depth = 1
    for idx in range(match.end(), len(content)):
        char = content[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[match.end():idx]
    return None


def match_residual_target(targets, name, default=1e-5):
    """Tolerância aplicável a um campo.

    Segue a convenção do OpenFOAM: a chave literal tem precedência sobre as
    expressões regulares, e a expressão precisa casar o nome inteiro do campo
    (`p` não pode capturar `epsilon`). Chaves com expressão inválida são
    comparadas literalmente.
    """
    if name in targets:
        return targets[name]

    for key, value in targets.items():
        try:
            if re.fullmatch(key, name):
                return value
        except re.error:
            continue
    return default
