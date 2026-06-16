"""Blueprint — POST /api/dwg-to-dxf  (v0.2.0)

Recebe arquivos .dwg via multipart/form-data e retorna um stream SSE
com o progresso da conversão via ODAFileConverter.exe.
"""

import tempfile
from pathlib import Path

from flask import Blueprint, Response, current_app, request, stream_with_context

from utils.paths import resolve_output

bp = Blueprint("dwg_to_dxf", __name__, url_prefix="/api")


@bp.post("/dwg-to-dxf")
def dwg_to_dxf():
    files      = request.files.getlist("files[]")
    oda_path   = request.form.get("oda_path", "").strip()
    version    = request.form.get("version", "ACAD2013").strip()
    audit      = int(request.form.get("audit", 0))
    dest_folder = request.form.get("dest_folder", "").strip()

    # Resolve caminho do ODA: usa o form, depois busca automático
    if not oda_path:
        from utils.deps import find_oda
        oda_path = find_oda() or ""

    if not files or all(f.filename == "" for f in files):
        return {"error": "Nenhum arquivo enviado."}, 400

    # Salva DWGs em pasta temporária
    tmp_dir    = Path(tempfile.mkdtemp(prefix="cad_upload_"))
    saved: list[Path] = []
    for f in files:
        if f.filename:
            dest = tmp_dir / Path(f.filename).name
            f.save(dest)
            saved.append(dest)

    output_dir = resolve_output(dest_folder)

    def generate():
        from services.oda_converter import run_oda
        yield from run_oda(saved, output_dir, oda_path=oda_path, version=version, audit=audit)
        # Limpeza do diretório de upload
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
