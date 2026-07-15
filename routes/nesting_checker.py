"""Blueprint — POST /api/nesting-check  (v0.9.0)

Recebe arquivos DXF (upload) ou o caminho de uma pasta no servidor
e verifica quais nestings são geometricamente idênticos.

Dois modos de input:
    files[]:  Upload direto de .dxf — tem prioridade se presente.
    folder:   Caminho de pasta no servidor (selecionável via
              /api/browse-folder) — usado quando não há upload.

Retorna stream SSE com progresso, relatório no log e link de download
de um ZIP contendo o relatório .txt.
"""

import tempfile
from pathlib import Path

from flask import Blueprint, Response, request, stream_with_context

from utils.paths import resolve_output

bp = Blueprint("nesting_checker", __name__, url_prefix="/api")


@bp.post("/nesting-check")
def nesting_check():
    files       = request.files.getlist("files[]")
    folder      = request.form.get("folder", "").strip()
    dest_folder = request.form.get("dest_folder", "").strip()

    saved: list[Path] = []
    nome_pasta = ""
    tmp_dir = None

    # Modo 1 — upload de arquivos
    has_upload = files and any(f.filename for f in files)
    if has_upload:
        tmp_dir = Path(tempfile.mkdtemp(prefix="cad_nesting_in_"))
        for f in files:
            if f.filename and Path(f.filename).suffix.lower() == ".dxf":
                dest = tmp_dir / Path(f.filename).name
                f.save(dest)
                saved.append(dest)
        nome_pasta = "upload direto"

    # Modo 2 — pasta no servidor
    elif folder and Path(folder).is_dir():
        pasta_path = Path(folder)
        saved = list(pasta_path.glob("*.[dD][xX][fF]"))
        nome_pasta = pasta_path.name

    else:
        return {"error": "Informe uma pasta válida ou envie arquivos DXF."}, 400

    if not saved:
        return {"error": "Nenhum arquivo .dxf encontrado."}, 400

    output_dir = resolve_output(dest_folder)

    def generate():
        from services.nesting_checker import verificar_nestings
        yield from verificar_nestings(saved, dest_dir=output_dir, nome_pasta=nome_pasta)
        if tmp_dir:
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
