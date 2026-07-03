"""Blueprint — POST /api/direcionamento-excel  (v0.8.0)

Recebe uma planilha Excel (.xlsx/.xls) via multipart/form-data e retorna
um stream SSE com o progresso do cálculo de direcionamento e a geração
da planilha formatada de saída.

Diferente das rotas de DXF/DWG/PDF, esta aceita um único arquivo por vez
(a lógica de negócio opera sobre a planilha inteira, não faz sentido
processar vários arquivos independentes num mesmo lote).
"""

import tempfile
from pathlib import Path

from flask import Blueprint, Response, request, stream_with_context

from utils.paths import resolve_output

bp = Blueprint("direcionamento", __name__, url_prefix="/api")


@bp.post("/direcionamento-excel")
def direcionamento_excel():
    file = request.files.get("file")
    dest_folder = request.form.get("dest_folder", "").strip()

    if not file or not file.filename:
        return {"error": "Nenhum arquivo enviado."}, 400

    if Path(file.filename).suffix.lower() not in (".xlsx", ".xls"):
        return {"error": "Formato inválido — envie um arquivo .xlsx ou .xls."}, 400

    # Salva o Excel em pasta temporária
    tmp_dir = Path(tempfile.mkdtemp(prefix="cad_direcionamento_in_"))
    saved_path = tmp_dir / Path(file.filename).name
    file.save(saved_path)

    output_dir = resolve_output(dest_folder)

    def generate():
        from services.direcionamento_excel import processar_direcionamento
        yield from processar_direcionamento(saved_path, dest_dir=output_dir)
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
