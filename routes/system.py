"""Blueprint de rotas utilitárias do sistema.

GET  /                          → index.html
GET  /api/browse-folder         → abre diálogo de pasta nativo (tkinter)
GET  /api/deps                  → status de dependências
GET  /api/detect-oda            → detecta ODAFileConverter.exe
GET  /api/detect-accore         → detecta accoreconsole.exe
GET  /api/download/<filename>   → serve arquivo da pasta output/
GET  /api/shutdown              → encerra o processo Flask
"""

import os
import signal

from flask import Blueprint, current_app, jsonify, render_template, send_from_directory

bp = Blueprint("system", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/api/browse-folder")
def browse_folder():
    """Abre diálogo de seleção de pasta via tkinter (precisa de display no servidor)."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        folder = filedialog.askdirectory(parent=root, title="Selecionar pasta de destino")
        root.destroy()

        if folder:
            return jsonify({"folder": folder, "ok": True})
        return jsonify({"folder": "", "ok": False, "msg": "Nenhuma pasta selecionada."})
    except Exception as exc:
        return jsonify({"folder": "", "ok": False, "msg": str(exc)}), 500


@bp.get("/api/deps")
def deps():
    from utils.deps import check_all_deps
    return jsonify(check_all_deps())


@bp.get("/api/detect-oda")
def detect_oda():
    from utils.deps import find_oda
    path = find_oda()
    return jsonify({"path": path or "", "found": path is not None})


@bp.get("/api/detect-accore")
def detect_accore():
    from utils.deps import find_accore
    path = find_accore()
    return jsonify({"path": path or "", "found": path is not None})


@bp.get("/api/download/<filename>")
def download(filename: str):
    output_dir = current_app.config["OUTPUT_DIR"]
    return send_from_directory(output_dir, filename, as_attachment=True)


@bp.get("/api/shutdown")
def shutdown():
    os.kill(os.getpid(), signal.SIGTERM)
    return jsonify({"ok": True, "msg": "Encerrando..."})
