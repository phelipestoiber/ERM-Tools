"""Helpers de caminhos.

get_resource_path  — resolve sys._MEIPASS quando congelado pelo PyInstaller.
resolve_output     — valida pasta de destino ou cai de volta em output/.
"""

import os
import sys


def get_resource_path(relative_path: str) -> str:
    """Retorna o caminho absoluto para um recurso empacotado.

    Quando o app está congelado pelo PyInstaller, os arquivos ficam em
    sys._MEIPASS. Em modo dev, resolve a partir do diretório do script.
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        base = os.path.dirname(base)  # sobe um nível (raiz do projeto)
    return os.path.join(base, relative_path)


def resolve_output(dest_folder: str | None = None) -> str:
    """Retorna uma pasta de destino válida.

    Se *dest_folder* for None, vazio, ou não existir, usa app_root/output/.
    Cria o diretório se necessário.
    """
    from flask import current_app

    if dest_folder and os.path.isdir(dest_folder):
        return dest_folder

    fallback = current_app.config.get("OUTPUT_DIR", "output")
    os.makedirs(fallback, exist_ok=True)
    return fallback
