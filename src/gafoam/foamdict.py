"""Leitura e escrita dos dicionários de um caso OpenFOAM.

Módulo sem dependência de Qt, para que a manipulação dos arquivos do caso
possa ser testada isoladamente da interface.
"""

import os
import re

# Subdiretórios obrigatórios de um caso OpenFOAM.
REQUIRED_CASE_DIRS = ("0", "constant", "system")

# Chaves do controlDict expostas na interface.
CONTROL_DICT_KEYS = (
    "application",
    "startFrom",
    "startTime",
    "stopAt",
    "endTime",
    "deltaT",
    "writeControl",
    "writeInterval",
    "purgeWrite",
    "adjustTimeStep",
    "maxCo",
)

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


def verify_case(case_path):
    """Executa uma verificação global da integridade do caso OpenFOAM antes da execução.
    
    Retorna uma tupla (is_valid: bool, issues: list[str], warnings: list[str]).
    """
    issues = []
    warnings = []
    
    if not case_path or not os.path.isdir(case_path):
        return False, ["Case directory does not exist or is invalid."], []
        
    # 1. Pastas obrigatórias
    missing_dirs = validate_case_dirs(case_path)
    if missing_dirs:
        issues.append(f"Missing required directories: {', '.join(missing_dirs)}")
        
    # 2. Dicionários essenciais do system/
    sys_dir = os.path.join(case_path, "system")
    for dict_name in ("controlDict", "fvSchemes", "fvSolution"):
        d_path = os.path.join(sys_dir, dict_name)
        if not os.path.isfile(d_path):
            issues.append(f"Missing required dictionary: 'system/{dict_name}'")
            
    # 3. Solver declarado no controlDict
    ctrl_dict = control_dict_path(case_path)
    if os.path.isfile(ctrl_dict):
        params = read_control_dict(case_path)
        if not params.get("application"):
            warnings.append("'application' solver is not specified in 'system/controlDict'")
            
    # 4. Malha (constant/polyMesh)
    poly_mesh_dir = os.path.join(case_path, "constant", "polyMesh")
    has_poly_mesh = os.path.isdir(poly_mesh_dir) and (
        os.path.isfile(os.path.join(poly_mesh_dir, "points")) or
        os.path.isfile(os.path.join(poly_mesh_dir, "faces")) or
        os.path.isfile(os.path.join(poly_mesh_dir, "boundary"))
    )
    if not has_poly_mesh:
        issues.append(
            "Mesh not found in 'constant/polyMesh'. Please run mesh generation (blockMesh or mesh.sh) first."
        )
        
    # 5. Configuração Paralela
    decomp_dict = os.path.join(sys_dir, "decomposeParDict")
    if os.path.isfile(decomp_dict):
        try:
            with open(decomp_dict, "r", encoding="utf-8", errors="ignore") as f:
                content = strip_comments(f.read())
            m = re.search(r"numberOfSubdomains\s+(\d+)\s*;", content)
            if m:
                n_sub = int(m.group(1))
                if n_sub < 1:
                    issues.append(f"Invalid numberOfSubdomains in decomposeParDict: {n_sub}")
        except Exception:
            pass

    # 6. Condições iniciais (0/ ou 0.orig/)
    zero_dir = os.path.join(case_path, "0")
    if os.path.isdir(zero_dir):
        try:
            zero_files = [f for f in os.listdir(zero_dir) if not f.startswith(".")]
            if not zero_files:
                warnings.append("Directory '0/' is empty. Initial conditions may be missing.")
        except Exception:
            pass
    elif os.path.isdir(os.path.join(case_path, "0.orig")):
        warnings.append("'0.orig/' exists but '0/' was not created yet.")

    return len(issues) == 0, issues, warnings


# ---------------------------------------------------------------------------
# Boundary Condition parsing (Feature 3)
# ---------------------------------------------------------------------------

# Files in 0/ that are NOT field files (skip these in the BC editor).
_SKIP_ZERO_FILES = {"uniform", "include"}

# Header pattern for the FoamFile block (kept for reference detection).
RE_BOUNDARY_FIELD = re.compile(r"boundaryField\s*\{")


def list_field_files(case_path):
    """List valid field files inside the ``0/`` directory.

    Returns a sorted list of basenames (e.g. ``['U', 'k', 'omega', 'p']``).
    Skips hidden files, directories, and known non-field entries.
    """
    zero_dir = os.path.join(case_path, "0")
    if not os.path.isdir(zero_dir):
        zero_dir = os.path.join(case_path, "0.orig")
    if not os.path.isdir(zero_dir):
        return []

    fields = []
    for name in os.listdir(zero_dir):
        if name.startswith(".") or name in _SKIP_ZERO_FILES:
            continue
        full = os.path.join(zero_dir, name)
        if os.path.isfile(full):
            fields.append(name)
    return sorted(fields)


def read_boundary_field(file_path):
    """Parse the ``boundaryField`` block from a field file.

    Returns a dict ``{patch_name: {key: value, ...}}``.  Every patch dict
    always contains at least the ``type`` key.  Additional keys (``value``,
    ``gradient``, etc.) are preserved as raw strings.
    """
    if not os.path.isfile(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return {}

    block = _extract_braced_block(content, RE_BOUNDARY_FIELD)
    if block is None:
        return {}

    result = {}
    # Match patch sub-blocks:  patchName { ... }
    patch_re = re.compile(r"(\w+)\s*\{")
    pos = 0
    while pos < len(block):
        m = patch_re.search(block, pos)
        if not m:
            break
        patch_name = m.group(1)
        # Extract braced content after patch name
        depth = 1
        start = m.end()
        idx = start
        while idx < len(block) and depth > 0:
            if block[idx] == "{":
                depth += 1
            elif block[idx] == "}":
                depth -= 1
            idx += 1
        inner = block[start:idx - 1] if depth == 0 else block[start:]

        # Parse key-value pairs from inner block
        patch_data = {}
        for kv in re.finditer(r"(\w+)\s+([^;]+);", inner):
            patch_data[kv.group(1).strip()] = kv.group(2).strip()

        result[patch_name] = patch_data
        pos = idx

    return result


def write_boundary_field(file_path, boundaries):
    """Update the ``boundaryField`` block in a field file.

    ``boundaries`` is a dict ``{patch_name: {key: value, ...}}``.
    The function replaces the entire ``boundaryField`` block while keeping
    the rest of the file intact (header, dimensions, internalField, etc.).
    """
    if not os.path.isfile(file_path):
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return False

    m = RE_BOUNDARY_FIELD.search(content)
    if not m:
        return False

    # Find the closing brace of boundaryField
    depth = 1
    start = m.end()
    idx = start
    while idx < len(content) and depth > 0:
        if content[idx] == "{":
            depth += 1
        elif content[idx] == "}":
            depth -= 1
        idx += 1

    if depth != 0:
        return False

    # Build new boundaryField block
    lines = []
    for patch_name, data in boundaries.items():
        lines.append(f"    {patch_name}")
        lines.append("    {")
        for key, val in data.items():
            lines.append(f"        {key:<16}{val};")
        lines.append("    }")
    new_block = "\n".join(lines)

    new_content = content[:m.start()] + "boundaryField\n{\n" + new_block + "\n}" + content[idx:]

    try:
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(new_content)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# fvSchemes parsing (Feature 4)
# ---------------------------------------------------------------------------

# The scheme blocks we care about.
_SCHEME_BLOCKS = (
    "ddtSchemes",
    "gradSchemes",
    "divSchemes",
    "laplacianSchemes",
    "interpolationSchemes",
    "snGradSchemes",
)

RE_SCHEME_BLOCK = {
    name: re.compile(rf"{name}\s*\{{") for name in _SCHEME_BLOCKS
}


def read_fv_schemes(case_path):
    """Read the ``default`` entries from each scheme block in ``system/fvSchemes``.

    Returns ``{block_name: default_value}`` where ``default_value`` is the
    raw string (e.g. ``"Gauss linear"``).  Blocks without a ``default`` entry
    are omitted.
    """
    fpath = os.path.join(case_path, "system", "fvSchemes")
    if not os.path.isfile(fpath):
        return {}
    try:
        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return {}

    clean = strip_comments(content)
    result = {}
    for name, pat in RE_SCHEME_BLOCK.items():
        block = _extract_braced_block(clean, pat)
        if block is None:
            continue
        m = re.search(r"\bdefault\s+([^;]+);", block)
        if m:
            result[name] = m.group(1).strip()
    return result


def write_fv_schemes(case_path, values):
    """Update the ``default`` line in each scheme block of ``system/fvSchemes``.

    ``values`` maps block name to the new default value string.
    """
    fpath = os.path.join(case_path, "system", "fvSchemes")
    if not os.path.isfile(fpath):
        return False
    try:
        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return False

    for block_name, new_val in values.items():
        # Replace 'default  <old>;' inside the named block
        # We use a targeted regex that finds the block header and then the default line
        pattern = rf"({block_name}\s*\{{[^}}]*?\bdefault\s+)[^;]+(;)"
        content = re.sub(pattern, rf"\g<1>{new_val}\2", content, count=1)

    try:
        with open(fpath, "w", encoding="utf-8") as fh:
            fh.write(content)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# fvSolution parsing (Feature 4)
# ---------------------------------------------------------------------------

RE_PIMPLE = re.compile(r"\bPIMPLE\s*\{")
RE_SIMPLE = re.compile(r"\bSIMPLE\s*\{")
RE_RELAXATION = re.compile(r"\brelaxationFactors\s*\{")


def read_fv_solution(case_path):
    """Read algorithm parameters and relaxation factors from ``system/fvSolution``.

    Returns a dict with keys:
    - ``algorithm``: ``"PIMPLE"`` or ``"SIMPLE"`` (whichever is found).
    - ``algorithm_params``: ``{key: value}`` from the algorithm block.
    - ``relaxation_fields``: ``{field: factor}`` from ``relaxationFactors.fields``.
    - ``relaxation_equations``: ``{eq: factor}`` from ``relaxationFactors.equations``.
    """
    fpath = os.path.join(case_path, "system", "fvSolution")
    if not os.path.isfile(fpath):
        return {}
    try:
        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return {}

    clean = strip_comments(content)
    result = {}

    # Detect algorithm type
    for algo_name, algo_re in (("PIMPLE", RE_PIMPLE), ("SIMPLE", RE_SIMPLE)):
        block = _extract_braced_block(clean, algo_re)
        if block is not None:
            result["algorithm"] = algo_name
            params = {}
            for m in RE_DICT_ENTRY.finditer(block):
                params[m.group(1).strip()] = m.group(2).strip()
            result["algorithm_params"] = params
            break

    if "algorithm" not in result:
        result["algorithm"] = ""
        result["algorithm_params"] = {}

    # Relaxation factors
    result["relaxation_fields"] = {}
    result["relaxation_equations"] = {}
    relax_block = _extract_braced_block(clean, RE_RELAXATION)
    if relax_block is not None:
        # Sub-block: fields { ... }
        fields_re = re.compile(r"\bfields\s*\{")
        fb = _extract_braced_block(relax_block, fields_re)
        if fb:
            for m in RE_DICT_ENTRY.finditer(fb):
                try:
                    result["relaxation_fields"][m.group(1).strip()] = float(m.group(2))
                except ValueError:
                    pass
        # Sub-block: equations { ... }
        eq_re = re.compile(r"\bequations\s*\{")
        eb = _extract_braced_block(relax_block, eq_re)
        if eb:
            for m in RE_DICT_ENTRY.finditer(eb):
                try:
                    result["relaxation_equations"][m.group(1).strip()] = float(m.group(2))
                except ValueError:
                    pass

    return result


def write_fv_solution_params(case_path, algorithm_params=None, relaxation_fields=None, relaxation_equations=None):
    """Update algorithm parameters and relaxation factors in ``system/fvSolution``.

    Only the supplied keys are updated; unsupplied entries are left as-is.
    """
    fpath = os.path.join(case_path, "system", "fvSolution")
    if not os.path.isfile(fpath):
        return False
    try:
        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return False

    if algorithm_params:
        for key, val in algorithm_params.items():
            pattern = rf"(\b{key}\s+)[^;]+(;)"
            content = re.sub(pattern, rf"\g<1>{val}\2", content, count=1)

    if relaxation_fields:
        for field, factor in relaxation_fields.items():
            pattern = rf"(\b{field}\s+)[^;]+(;)"
            content = re.sub(pattern, rf"\g<1>{factor}\2", content, count=1)

    if relaxation_equations:
        for eq, factor in relaxation_equations.items():
            pattern = rf"(\b{eq}\s+)[^;]+(;)"
            content = re.sub(pattern, rf"\g<1>{factor}\2", content, count=1)

    try:
        with open(fpath, "w", encoding="utf-8") as fh:
            fh.write(content)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# decomposeParDict parsing & writing
# ---------------------------------------------------------------------------

def decompose_par_dict_path(case_path):
    return os.path.join(case_path, "system", "decomposeParDict")


def read_decompose_par_dict(case_path):
    """Read parallel decomposition parameters from ``system/decomposeParDict``."""
    dpath = decompose_par_dict_path(case_path)
    if not os.path.isfile(dpath):
        return {"numberOfSubdomains": "4", "method": "scotch"}
    try:
        with open(dpath, "r", encoding="utf-8") as f:
            clean = strip_comments(f.read())
    except OSError:
        return {"numberOfSubdomains": "4", "method": "scotch"}

    res = {}
    m_sub = re.search(r"\bnumberOfSubdomains\s+([0-9]+)\s*;", clean)
    res["numberOfSubdomains"] = m_sub.group(1) if m_sub else "4"

    m_meth = re.search(r"\bmethod\s+([a-zA-Z0-9_]+)\s*;", clean)
    res["method"] = m_meth.group(1) if m_meth else "scotch"
    return res


def write_decompose_par_dict(case_path, values):
    """Update or create ``system/decomposeParDict``."""
    dpath = decompose_par_dict_path(case_path)
    os.makedirs(os.path.dirname(dpath), exist_ok=True)

    num_sub = str(values.get("numberOfSubdomains", "4"))
    method = str(values.get("method", "scotch"))

    if os.path.isfile(dpath):
        try:
            with open(dpath, "r", encoding="utf-8") as f:
                content = f.read()

            if re.search(r"\bnumberOfSubdomains\b", content):
                content = re.sub(r"(\bnumberOfSubdomains\s+)[0-9]+(\s*;)", rf"\g<1>{num_sub}\g<2>", content)
            else:
                content += f"\nnumberOfSubdomains {num_sub};\n"

            if re.search(r"\bmethod\b", content):
                content = re.sub(r"(\bmethod\s+)[a-zA-Z0-9_]+(\s*;)", rf"\g<1>{method}\g<2>", content)
            else:
                content += f"\nmethod {method};\n"

            with open(dpath, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except OSError:
            return False
    else:
        # Create template decomposeParDict
        template = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      decomposeParDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

numberOfSubdomains {num_sub};

method          {method};

// ************************************************************************* //
"""
        try:
            with open(dpath, "w", encoding="utf-8") as f:
                f.write(template)
            return True
        except OSError:
            return False


# ---------------------------------------------------------------------------
# turbulenceProperties / momentumTransport parsing & writing
# ---------------------------------------------------------------------------

def turbulence_dict_path(case_path):
    # Check modern OpenFOAM momentumTransport first, fallback to turbulenceProperties
    p1 = os.path.join(case_path, "constant", "momentumTransport")
    if os.path.isfile(p1):
        return p1
    return os.path.join(case_path, "constant", "turbulenceProperties")


def read_turbulence_properties(case_path):
    """Read simulationType and model from turbulenceProperties / momentumTransport."""
    dpath = turbulence_dict_path(case_path)
    if not os.path.isfile(dpath):
        return {"simulationType": "RAS", "model": "kOmegaSST", "turbulence": "on"}
    try:
        with open(dpath, "r", encoding="utf-8") as f:
            clean = strip_comments(f.read())
    except OSError:
        return {"simulationType": "RAS", "model": "kOmegaSST", "turbulence": "on"}

    res = {}
    m_sim = re.search(r"\bsimulationType\s+([a-zA-Z0-9_]+)\s*;", clean)
    res["simulationType"] = m_sim.group(1) if m_sim else "RAS"

    # Search for RASModel, LESModel or model inside RAS/LES sub-blocks
    m_model = re.search(r"\b(?:RASModel|LESModel|model)\s+([a-zA-Z0-9_]+)\s*;", clean)
    res["model"] = m_model.group(1) if m_model else "kOmegaSST"

    m_turb = re.search(r"\bturbulence\s+(on|off)\s*;", clean)
    res["turbulence"] = m_turb.group(1) if m_turb else "on"
    return res


def write_turbulence_properties(case_path, values):
    """Update turbulence properties in constant/."""
    dpath = turbulence_dict_path(case_path)
    if not os.path.isfile(dpath):
        dpath = os.path.join(case_path, "constant", "turbulenceProperties")
    os.makedirs(os.path.dirname(dpath), exist_ok=True)

    sim_type = str(values.get("simulationType", "RAS"))
    model = str(values.get("model", "kOmegaSST"))
    turb = str(values.get("turbulence", "on"))

    if os.path.isfile(dpath):
        try:
            with open(dpath, "r", encoding="utf-8") as f:
                content = f.read()

            if re.search(r"\bsimulationType\b", content):
                content = re.sub(r"(\bsimulationType\s+)[a-zA-Z0-9_]+(\s*;)", rf"\g<1>{sim_type}\g<2>", content)

            if re.search(r"\bRASModel\b", content):
                content = re.sub(r"(\bRASModel\s+)[a-zA-Z0-9_]+(\s*;)", rf"\g<1>{model}\g<2>", content)
            elif re.search(r"\bLESModel\b", content):
                content = re.sub(r"(\bLESModel\s+)[a-zA-Z0-9_]+(\s*;)", rf"\g<1>{model}\g<2>", content)
            elif re.search(r"\bmodel\b", content):
                content = re.sub(r"(\bmodel\s+)[a-zA-Z0-9_]+(\s*;)", rf"\g<1>{model}\g<2>", content)

            if re.search(r"\bturbulence\b", content):
                content = re.sub(r"(\bturbulence\s+)[a-zA-Z0-9_]+(\s*;)", rf"\g<1>{turb}\g<2>", content)

            with open(dpath, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except OSError:
            return False
    else:
        template = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      turbulenceProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

simulationType  {sim_type};

RAS
{{
    RASModel        {model};
    turbulence      {turb};
    printCoeffs     on;
}}

// ************************************************************************* //
"""
        try:
            with open(dpath, "w", encoding="utf-8") as f:
                f.write(template)
            return True
        except OSError:
            return False


# ---------------------------------------------------------------------------
# transportProperties / physicalProperties parsing & writing
# ---------------------------------------------------------------------------

def transport_dict_path(case_path):
    p1 = os.path.join(case_path, "constant", "physicalProperties")
    if os.path.isfile(p1):
        return p1
    return os.path.join(case_path, "constant", "transportProperties")


def read_transport_properties(case_path):
    """Read viscosity nu and density rho from transportProperties / physicalProperties."""
    dpath = transport_dict_path(case_path)
    if not os.path.isfile(dpath):
        return {"nu": "1e-05", "rho": "1000"}
    try:
        with open(dpath, "r", encoding="utf-8") as f:
            clean = strip_comments(f.read())
    except OSError:
        return {"nu": "1e-05", "rho": "1000"}

    res = {}
    # Matches: nu [0 2 -1 0 0 0 0] 1e-05; or nu 1e-05;
    m_nu = re.search(r"\bnu\s+(?:\[[^\]]*\]\s*)?([0-9eE\.\-]+)\s*;", clean)
    res["nu"] = m_nu.group(1) if m_nu else "1e-05"

    m_rho = re.search(r"\brho\s+(?:\[[^\]]*\]\s*)?([0-9eE\.\-]+)\s*;", clean)
    res["rho"] = m_rho.group(1) if m_rho else "1000"
    return res


def write_transport_properties(case_path, values):
    """Update viscosity nu and density rho in constant/transportProperties."""
    dpath = transport_dict_path(case_path)
    if not os.path.isfile(dpath):
        dpath = os.path.join(case_path, "constant", "transportProperties")
    os.makedirs(os.path.dirname(dpath), exist_ok=True)

    nu_val = str(values.get("nu", "1e-05"))
    rho_val = str(values.get("rho", "1000"))

    if os.path.isfile(dpath):
        try:
            with open(dpath, "r", encoding="utf-8") as f:
                content = f.read()

            if re.search(r"\bnu\b", content):
                content = re.sub(
                    r"(\bnu\s+(?:\[[^\]]*\]\s*)?)[0-9eE\.\-]+(\s*;)",
                    rf"\g<1>{nu_val}\g<2>",
                    content,
                    count=1
                )

            if re.search(r"\brho\b", content):
                content = re.sub(
                    r"(\brho\s+(?:\[[^\]]*\]\s*)?)[0-9eE\.\-]+(\s*;)",
                    rf"\g<1>{rho_val}\g<2>",
                    content,
                    count=1
                )

            with open(dpath, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except OSError:
            return False
    else:
        template = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      transportProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

transportModel  Newtonian;

nu              [ 0 2 -1 0 0 0 0 ] {nu_val};

rho             [ 1 -3 0 0 0 0 0 ] {rho_val};

// ************************************************************************* //
"""
        try:
            with open(dpath, "w", encoding="utf-8") as f:
                f.write(template)
            return True
        except OSError:
            return False


