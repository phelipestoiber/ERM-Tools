"""Blueprint — POST /api/dxf-scale  (v0.3.0)

Recebe arquivos .dxf via multipart/form-data e retorna um stream SSE
com o progresso do escalonamento de entidades via ezdxf.
"""

import tempfile
from pathlib import Path

from flask import Blueprint, Response, request, stream_with_context

from utils.paths import resolve_output

bp = Blueprint("dxf_scale", __name__, url_prefix="/api")


@bp.post("/dxf-scale")
def dxf_scale():
    files       = request.files.getlist("files[]")
    factor_raw  = request.form.get("factor", "").strip()
    suffix      = request.form.get("suffix", "_scaled").strip() or "_scaled"
    dest_folder = request.form.get("dest_folder", "").strip()

    if not files or all(f.filename == "" for f in files):
        return {"error": "Nenhum arquivo enviado."}, 400

    try:
        factor = float(factor_raw)
    except ValueError:
        return {"error": "Fator de escala inválido."}, 400

    if factor <= 0:
        return {"error": "Fator de escala deve ser maior que zero."}, 400

    # Salva DXFs em pasta temporária
    tmp_dir = Path(tempfile.mkdtemp(prefix="cad_scale_in_"))
    saved: list[Path] = []
    for f in files:
        if f.filename:
            dest = tmp_dir / Path(f.filename).name
            f.save(dest)
            saved.append(dest)

    output_dir = resolve_output(dest_folder)

    def generate():
        from services.dxf_scaler import scale_dxf
        yield from scale_dxf(saved, factor=factor, suffix=suffix, dest_dir=output_dir)
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
