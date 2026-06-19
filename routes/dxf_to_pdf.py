"""Blueprint — POST /api/dxf-to-pdf  (v0.4.0)

Recebe arquivos .dxf (ou .dwg — pipeline encadeado, v0.6.0) via
multipart/form-data e retorna um stream SSE com o progresso da
renderização para PDF via ezdxf.addons.drawing + matplotlib.
"""

import tempfile
from pathlib import Path

from flask import Blueprint, Response, request, stream_with_context

from utils.paths import resolve_output

bp = Blueprint("dxf_to_pdf", __name__, url_prefix="/api")


@bp.post("/dxf-to-pdf")
def dxf_to_pdf():
    files       = request.files.getlist("files[]")
    paper       = request.form.get("paper", "A4").strip()
    orientation = request.form.get("orientation", "landscape").strip()
    color_mode  = request.form.get("color_mode", "color").strip()
    dest_folder = request.form.get("dest_folder", "").strip()

    if not files or all(f.filename == "" for f in files):
        return {"error": "Nenhum arquivo enviado."}, 400

    if paper not in ("A4", "A3", "A2", "A1"):
        return {"error": "Tamanho de papel inválido."}, 400

    if orientation not in ("portrait", "landscape"):
        return {"error": "Orientação inválida."}, 400

    if color_mode not in ("color", "bw"):
        return {"error": "Modo de cor inválido."}, 400

    # Salva arquivos em pasta temporária
    tmp_dir = Path(tempfile.mkdtemp(prefix="cad_pdf_in_"))
    saved_dxf: list[Path] = []
    saved_dwg: list[Path] = []
    for f in files:
        if not f.filename:
            continue
        dest = tmp_dir / Path(f.filename).name
        f.save(dest)
        if dest.suffix.lower() == ".dwg":
            saved_dwg.append(dest)
        else:
            saved_dxf.append(dest)

    output_dir = resolve_output(dest_folder)

    def generate():
        from services.dxf_renderer import render_to_pdf
        from utils.sse import sse_fail, sse_log

        if saved_dwg:
            # Pipeline DWG → PDF encadeado (ODA + renderer) — v0.6.0
            yield sse_log(
                f"{len(saved_dwg)} arquivo(s) .dwg detectado(s) — conversão "
                "DWG→PDF encadeada será implementada na v0.6.0."
            )
            for dwg in saved_dwg:
                yield sse_fail(dwg.name, "Conversão direta de DWG ainda não implementada (use DWG→DXF primeiro)")

        if saved_dxf:
            yield from render_to_pdf(
                saved_dxf, paper=paper, orientation=orientation,
                color_mode=color_mode, dest_dir=output_dir,
            )
        else:
            from utils.sse import sse_done
            yield sse_done()

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
