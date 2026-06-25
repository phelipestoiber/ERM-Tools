"""Blueprint — Editor de PDF (merge)  (v0.5.0)

POST /api/pdf-stage   — recebe PDFs, salva em staging, retorna metadados
                         (file_id, nome, nº páginas, tamanho) de cada um.
POST /api/pdf-merge   — recebe a sequência final de páginas e monta o PDF
                         mesclado. Retorna JSON (não usa SSE — operação
                         rápida).
"""

import json

from flask import Blueprint, current_app, jsonify, request

from utils.paths import resolve_output
from utils.zip_utils import create_zip

bp = Blueprint("pdf_merge", __name__, url_prefix="/api")


@bp.post("/pdf-stage")
def pdf_stage():
    files = request.files.getlist("files[]")

    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "Nenhum arquivo enviado."}), 400

    from services.pdf_editor import stage_files

    staging_dir = current_app.config["STAGING_DIR"]
    result = stage_files(files, staging_dir)

    return jsonify(result)


@bp.post("/pdf-merge")
def pdf_merge():
    sequence_raw = request.form.get("sequence", "") or (
        request.json.get("sequence") if request.is_json else None
    )
    dest_folder = (
        request.form.get("dest_folder", "")
        if not request.is_json
        else request.json.get("dest_folder", "")
    ).strip()

    if not sequence_raw:
        return jsonify({"error": "Sequência de páginas não informada."}), 400

    try:
        sequence = (
            json.loads(sequence_raw) if isinstance(sequence_raw, str) else sequence_raw
        )
    except json.JSONDecodeError:
        return jsonify({"error": "Sequência de páginas inválida (JSON malformado)."}), 400

    if not isinstance(sequence, list) or not sequence:
        return jsonify({"error": "Sequência de páginas vazia ou inválida."}), 400

    from services.pdf_editor import merge_pdfs

    staging_dir = current_app.config["STAGING_DIR"]

    # Monta o PDF mesclado numa pasta temporária e depois empacota em zip
    # na pasta de destino final.
    import tempfile
    tmp_merge_dir = tempfile.mkdtemp(prefix="cad_merge_")

    try:
        merge_result = merge_pdfs(sequence, staging_dir=staging_dir, out_dir=tmp_merge_dir)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Falha ao mesclar PDFs: {exc}"}), 500

    output_dir = resolve_output(dest_folder)

    from pathlib import Path
    pdf_path = Path(tmp_merge_dir) / merge_result["pdf"]
    zip_name = create_zip([pdf_path], output_dir, prefix="pdf_merge")

    import shutil
    shutil.rmtree(tmp_merge_dir, ignore_errors=True)

    return jsonify({
        "zip": zip_name,
        "pdf": merge_result["pdf"],
        "n_pages": merge_result["n_pages"],
        "size_bytes": merge_result["size_bytes"],
    })
