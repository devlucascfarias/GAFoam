"""Verificação sintática de dicionários do OpenFOAM.

Módulo sem dependência de Qt. Trabalha sobre uma versão do texto com
comentários, strings e código C++ embutido neutralizados, de forma que o
cabeçalho padrão do OpenFOAM e as listas multilinha não gerem alarmes falsos.
"""

import os
import re

RE_STRING = re.compile(r'"[^"\n]*"')

OPENING = "{[("
CLOSING = "}])"
PAIRS = {"}": "{", "]": "[", ")": "("}

# Linhas terminadas por estes caracteres não esperam ponto e vírgula.
NO_SEMICOLON_SUFFIX = ("{", "}", "(", ")", "[", "]", ";", "\\", ",")

# Uma entrada continua na linha seguinte quando esta abre um bloco ou lista.
CONTINUATION_PREFIX = ("{", "(", "[")

RE_NUMERIC = re.compile(r"^[\d.eE+-]+$")


def clean_lines(text):
    """Linhas do texto sem comentários, strings ou blocos `#{ ... #}`.

    A lista devolvida tem o mesmo comprimento do texto original, para que os
    índices continuem correspondendo aos números de linha exibidos ao usuário.
    """
    result = []
    in_block_comment = False
    in_code_block = False

    for raw in text.split("\n"):
        line = raw
        out = []
        i = 0
        while i < len(line):
            two = line[i:i + 2]
            if in_block_comment:
                if two == "*/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue
            if in_code_block:
                # Código C++ embutido: só o delimitador de fechamento importa.
                if two == "#}":
                    in_code_block = False
                    i += 2
                    continue
                i += 1
                continue
            if two == "//":
                break
            if two == "/*":
                in_block_comment = True
                i += 2
                continue
            if two == "#{":
                in_code_block = True
                i += 2
                continue
            out.append(line[i])
            i += 1

        # Strings viram um token opaco: preserva a contagem de tokens sem
        # deixar que aspas contenham delimitadores ou pontos e vírgulas.
        result.append(RE_STRING.sub('"s"', "".join(out)))

    return result


def check_brackets(lines):
    """Primeiro erro de balanceamento de `{}`, `[]` ou `()`, se houver."""
    stack = []
    for number, line in enumerate(lines, start=1):
        for char in line:
            if char in OPENING:
                stack.append((char, number))
            elif char in CLOSING:
                if not stack:
                    return f"Caractere '{char}' de fechamento inesperado na linha {number}"
                top, opened_at = stack.pop()
                if PAIRS[char] != top:
                    return (
                        f"Chave/parêntese incorreto na linha {number} "
                        f"(esperava fechar '{top}' aberto na linha {opened_at})"
                    )
    if stack:
        top, opened_at = stack[-1]
        return f"Chave/parêntese '{top}' aberto na linha {opened_at} nunca foi fechado"
    return None


def _next_significant(lines, start):
    """Próxima linha não vazia a partir de `start`, ou string vazia."""
    for line in lines[start:]:
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def check_semicolons(lines):
    """Primeira entrada aparentemente sem `;` de terminação, se houver.

    Entradas dentro de listas (`( ... )`) são ignoradas: nelas os valores são
    separados por espaço, sem ponto e vírgula.
    """
    list_depth = 0

    for index, line in enumerate(lines):
        stripped = line.strip()
        opens = line.count("(") + line.count("[")
        closes = line.count(")") + line.count("]")

        inside_list = list_depth > 0
        list_depth = max(0, list_depth + opens - closes)

        if inside_list or not stripped:
            continue
        # Diretivas (#include, #calc) e macros ($internalField) têm regras próprias.
        if stripped.startswith(("#", "$")):
            continue
        if stripped.endswith(NO_SEMICOLON_SUFFIX):
            continue
        if ";" in stripped:
            continue

        tokens = stripped.split()
        if len(tokens) < 2:
            # Nome isolado: cabeçalho de sub-dicionário ou de lista.
            continue

        following = _next_significant(lines, index + 1)
        if following.startswith(CONTINUATION_PREFIX) or RE_NUMERIC.match(following):
            # A entrada continua na próxima linha (sub-dicionário, lista ou
            # campo `nonuniform List<...>` com a contagem na linha seguinte).
            continue

        return f"Possível ponto e vírgula ';' ausente na linha {index + 1}"

    return None


def is_openfoam_dict(file_path=None, text=""):
    """Determina se um arquivo ou conteúdo é um dicionário OpenFOAM (sujeito a lint).

    Arquivos de log, scripts de shell, binários ou textos comuns não devem ser
    validados pelo linter de dicionários.
    """
    if file_path:
        base = os.path.basename(file_path).lower()
        if base.startswith("log.") or base.endswith(
            (".log", ".sh", ".py", ".txt", ".csv", ".dat", ".stl", ".obj", ".png", ".jpg", ".md", ".json")
        ):
            return False
        if base in ("allrun", "allclean", "makefile", ".gitignore", "readme"):
            return False

    if text:
        first_chunk = text[:2000]
        # Logs de execução do OpenFOAM contêm campos como 'Build :', 'Exec :' ou 'PID :'
        if re.search(r"^\s*(Build\s*:|Exec\s*:|Host\s*:|PID\s*:|I/O\s*:|Slaves\s*:)", first_chunk, re.MULTILINE):
            return False

    return True


def check_syntax(text, file_path=None):
    """Lista de problemas encontrados no dicionário (vazia se estiver íntegro ou se não for um dicionário).

    Retorna no máximo um problema por vez: o primeiro erro estrutural costuma
    tornar os seguintes irrelevantes.
    """
    if not is_openfoam_dict(file_path, text):
        return []

    lines = clean_lines(text)

    error = check_brackets(lines)
    if error:
        return [error]

    error = check_semicolons(lines)
    if error:
        return [error]

    return []
