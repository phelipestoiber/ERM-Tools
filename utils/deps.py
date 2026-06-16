"""Verificador de dependências em tempo de execução."""

import os

# Caminhos padrão onde o ODA File Converter costuma ser instalado no Windows
_ODA_CANDIDATES = [
    r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe",
    r"C:\Program Files\ODA File Converter\ODAFileConverter.exe",
]

# Caminhos padrão do accoreconsole.exe (AutoCAD)
_ACCORE_CANDIDATES = [
    r"C:\Program Files\Autodesk\AutoCAD 2025\accoreconsole.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2024\accoreconsole.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2023\accoreconsole.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2022\accoreconsole.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2021\accoreconsole.exe",
]


def _check_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def find_oda() -> str | None:
    """Retorna o caminho do ODA File Converter, ou None se não encontrado."""
    for path in _ODA_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def find_accore() -> str | None:
    """Retorna o caminho do accoreconsole.exe, ou None se não encontrado."""
    for path in _ACCORE_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def check_all_deps() -> dict:
    """Retorna um dict com o status de todas as dependências."""
    oda = find_oda()
    accore = find_accore()

    return {
        "ezdxf": _check_import("ezdxf"),
        "pypdf": _check_import("pypdf"),
        "matplotlib": _check_import("matplotlib"),
        "oda_found": oda is not None,
        "oda_path": oda,
        "accore_found": accore is not None,
        "accore_path": accore,
    }
