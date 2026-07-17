"""Blueprint — POST /api/comparar-pecas  (v0.10.0)

Recebe uma planilha Excel (.xlsx/.xls) e um parâmetro `modo` via
multipart/form-data e retorna um stream SSE com o progresso da análise.

Modos disponíveis:
    familias — detecta peças de famílias DIFERENTES com peso/área idênticos
    copias   — detecta cópias (_C##) que divergem do original

Parâmetros de tolerância são opcionais; os defaults estão nos services.
"""

import tempfile
from pathlib import Path

from flask import Blueprint, Response, request, stream_with_context

from utils.paths import resolve_output

bp = Blueprint("comparador", __name__, url_prefix="/api")

_MODOS_VALIDOS = ("familias", "copias")


def _to_float_safe(raw: str | None, default: float) -> float:
    """Converte string para float com fallback seguro."""
    if not raw or raw.strip() == "":
        return default
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError:
        return default


@bp.post("/comparar-pecas")
def comparar_pecas():
    file        = request.files.get("file")
    modo        = request.form.get("modo", "").strip()
    dest_folder = request.form.get("dest_folder", "").strip()

    if not file or not file.filename:
        return {"error": "Nenhum arquivo enviado."}, 400

    if Path(file.filename).suffix.lower() not in (".xlsx", ".xls"):
        return {"error": "Formato inválido — envie um arquivo .xlsx ou .xls."}, 400

    if modo not in _MODOS_VALIDOS:
        return {"error": f"Modo inválido. Use: {', '.join(_MODOS_VALIDOS)}"}, 400

    # Coleta tolerâncias do modo correto
    if modo == "familias":
        params = {
            "tol_peso": _to_float_safe(request.form.get("tol_peso"), 0.009),
            "tol_area": _to_float_safe(request.form.get("tol_area"), 0.009),
        }
    else:  # copias
        params = {
            "tol_verdadeira": _to_float_safe(request.form.get("tol_verdadeira"), 0.001),
            "tol_grupo":      _to_float_safe(request.form.get("tol_grupo"),      0.010),
        }

    # Salva arquivo em pasta temporária
    tmp_dir     = Path(tempfile.mkdtemp(prefix="cad_comp_in_"))
    saved_path  = tmp_dir / Path(file.filename).name
    file.save(saved_path)

    output_dir = resolve_output(dest_folder)

    def generate():
        from services.comparador_pecas import (
            verificar_familias_duplicadas,
            verificar_copias_divergentes,
        )

        if modo == "familias":
            yield from verificar_familias_duplicadas(saved_path, params, output_dir)
        else:
            yield from verificar_copias_divergentes(saved_path, params, output_dir)

        # Limpeza do diretório de upload
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
