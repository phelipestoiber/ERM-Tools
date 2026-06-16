"""CAD Tools — Flask app factory + entry point."""

import os
import sys
import signal
import socket
import subprocess


def create_app():
    from flask import Flask

    # Resolve base path (handles PyInstaller frozen .exe)
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
        app_root = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        app_root = base_dir

    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB
    app.config["APP_ROOT"] = app_root

    # Output folder — created on boot
    output_dir = os.path.join(app_root, "output")
    os.makedirs(output_dir, exist_ok=True)
    app.config["OUTPUT_DIR"] = output_dir

    # Register Blueprints
    from routes.system import bp as system_bp
    app.register_blueprint(system_bp)

    from routes.dwg_to_dxf import bp as dwg_bp
    app.register_blueprint(dwg_bp)

    # Future blueprints registered here as phases are added:
    # from routes.dxf_scale   import bp as scale_bp # v0.3.0
    # from routes.dxf_to_pdf  import bp as pdf_bp   # v0.4.0
    # from routes.pdf_merge   import bp as merge_bp  # v0.5.0

    @app.errorhandler(500)
    def internal_error(exc):
        import traceback
        from flask import jsonify
        return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500

    return app


def _find_free_port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _open_chrome(port):
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    url = f"http://127.0.0.1:{port}"
    for path in candidates:
        if os.path.exists(path):
            subprocess.Popen([path, f"--app={url}"])
            return
    # Fallback: default browser
    import webbrowser
    webbrowser.open(url)


if __name__ == "__main__":
    port = _find_free_port()
    app = create_app()

    import threading
    threading.Timer(1.2, _open_chrome, args=(port,)).start()

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
