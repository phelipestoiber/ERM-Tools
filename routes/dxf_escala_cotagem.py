"""Blueprint — POST /api/dxf-escala-cotagem  (v0.7.0)

Recebe arquivos .dxf via multipart/form-data e retorna um stream SSE com o
progresso da cotagem automática (regra FORAN) + escala global + explosão
de blocos.
"""

import json
import tempfile
from pathlib import Path

from flask import Blueprint, Response, request, stream_with_context

from utils.paths import resolve_output

bp = Blueprint("dxf_escala_cotagem", __name__, url_prefix="/api")


def _to_bool(raw: str | None, default: bool = True) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip() in ("1", "true", "True", "on", "yes")


def _to_float(raw: str | None, default: float) -> float:
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@bp.post("/dxf-escala-cotagem")
def dxf_escala_cotagem():
    files       = request.files.getlist("files[]")
    escala_raw  = request.form.get("escala", "").strip()
    dest_folder = request.form.get("dest_folder", "").strip()

    if not files or all(f.filename == "" for f in files):
        return {"error": "Nenhum arquivo enviado."}, 400

    try:
        escala = float(escala_raw)
    except ValueError:
        return {"error": "Escala inválida."}, 400

    if escala <= 0:
        return {"error": "Escala deve ser maior que zero."}, 400

    # Parâmetros avançados (todos opcionais, com defaults no orquestrador)
    labels_raw = request.form.get("labels", "").strip()
    labels = None
    if labels_raw:
        try:
            parsed = json.loads(labels_raw)
            # Aceita tanto [{texto,x,y}, ...] quanto [[texto,x,y], ...]
            labels = [
                (item["texto"], float(item["x"]), float(item["y"]))
                if isinstance(item, dict) else
                (item[0], float(item[1]), float(item[2]))
                for item in parsed
            ]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError):
            return {"error": "Lista de labels inválida (JSON malformado)."}, 400

    params = {
        "escala": escala,
        "layer_cota": request.form.get("layer_cota", "").strip() or "Dimensions",
        "layer_textos_antigos": request.form.get("layer_textos_antigos", "Free Texts").strip(),
        "nome_bloco": request.form.get("nome_bloco", "").strip() or "PartBlock",
        "limite_y": _to_float(request.form.get("limite_y"), 2000),
        "raio_minimo": _to_float(request.form.get("raio_minimo"), 15.0),
        "tolerancia": _to_float(request.form.get("tolerancia"), 2.0),
        "tolerancia_borda": _to_float(request.form.get("tolerancia_borda"), 5.0),
        "explodir_blocos": _to_bool(request.form.get("explodir_blocos"), True),
        "labels": labels,
    }

    # Salva DXFs em pasta temporária
    tmp_dir = Path(tempfile.mkdtemp(prefix="cad_cotagem_in_"))
    saved: list[Path] = []
    for f in files:
        if f.filename:
            dest = tmp_dir / Path(f.filename).name
            f.save(dest)
            saved.append(dest)

    output_dir = resolve_output(dest_folder)

    def generate():
        from services.dxf_escala_cotagem import escalar_e_cotar
        yield from escalar_e_cotar(saved, params, dest_dir=output_dir)
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
