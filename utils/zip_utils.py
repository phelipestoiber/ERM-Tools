"""Utilitário para criação de arquivos ZIP."""

import zipfile
from pathlib import Path
from uuid import uuid4


def create_zip(files: list[Path], dest_dir: Path | str, prefix: str = "output") -> str:
    """Empacota *files* num único ZIP em *dest_dir*.

    Returns:
        Nome do arquivo zip gerado (apenas o nome, sem o caminho completo).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_name = f"{prefix}_{uuid4().hex[:8]}.zip"
    zip_path = dest_dir / zip_name

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            f = Path(f)
            if f.exists():
                zf.write(f, arcname=f.name)

    return zip_name
