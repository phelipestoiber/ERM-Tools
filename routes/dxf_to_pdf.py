"""Blueprint — POST /api/dxf-to-pdf  (v0.4.0 · pipeline DWG→PDF na v0.6.0)

Recebe arquivos .dxf e/ou .dwg via multipart/form-data e retorna um stream
SSE com o progresso da renderização para PDF via ezdxf.addons.drawing +
matplotlib. Arquivos .dwg passam primeiro por um pipeline encadeado:
ODA File Converter (DWG→DXF) seguido da mesma renderização DXF→PDF.
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
        import shutil
        from services.dxf_renderer import render_to_pdf
        from utils.sse import sse_done, sse_fail, sse_log

        # Arquivos .dxf que serão enviados ao renderizador — começa com os
        # .dxf enviados diretamente; .dwg convertidos são adicionados aqui.
        files_for_render: list[Path] = list(saved_dxf)
        dwg_dxf_temp_dir: Path | None = None

        try:
            if saved_dwg:
                from utils.deps import find_oda
                oda_path = find_oda()

                if not oda_path:
                    for dwg in saved_dwg:
                        yield sse_fail(
                            dwg.name,
                            "ODA File Converter não encontrado. Instale o ODA "
                            "File Converter para converter arquivos DWG "
                            "(https://www.opendesign.com/guestfiles/oda_file_converter).",
                        )
                else:
                    from services.oda_converter import convert_dwg_to_dxf_internal

                    dwg_dxf_temp_dir = Path(tempfile.mkdtemp(prefix="cad_pipeline_dxf_"))

                    for dwg in saved_dwg:
                        yield sse_log(f"Convertendo DWG para DXF: {dwg.name}")

                    try:
                        result = convert_dwg_to_dxf_internal(
                            saved_dwg, dwg_dxf_temp_dir, oda_path,
                            version="ACAD2013", audit=0,
                        )
                        for dxf_path in result["ok"]:
                            yield sse_log(f"OK {dxf_path.name} (DWG→DXF)")
                            files_for_render.append(dxf_path)
                        for name, reason in result["fail"]:
                            yield sse_fail(name, reason)
                    except Exception as exc:
                        for dwg in saved_dwg:
                            yield sse_fail(dwg.name, str(exc))

            if files_for_render:
                if saved_dwg:
                    yield sse_log("Gerando PDF a partir do(s) DXF...")
                yield from render_to_pdf(
                    files_for_render, paper=paper, orientation=orientation,
                    color_mode=color_mode, dest_dir=output_dir,
                )
            else:
                yield sse_done()

        finally:
            # Limpeza dos DXF intermediários gerados pelo ODA e da pasta
            # de upload original.
            if dwg_dxf_temp_dir:
                shutil.rmtree(dwg_dxf_temp_dir, ignore_errors=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
