"""SSE event helpers.

Tipos válidos: LOG | OK | FAIL | DOWNLOAD | DONE

Formato do stream:
    data: TIPO payload\n\n

No frontend: event.data.split(' ', 1) → [tipo, payload]
"""


def sse_event(tipo: str, payload: str = "") -> str:
    """Retorna uma linha de evento SSE formatada."""
    if payload:
        return f"data: {tipo} {payload}\n\n"
    return f"data: {tipo}\n\n"


def sse_log(msg: str) -> str:
    return sse_event("LOG", msg)


def sse_ok(filename: str) -> str:
    return sse_event("OK", filename)


def sse_fail(filename: str, reason: str = "") -> str:
    payload = f"{filename}: {reason}" if reason else filename
    return sse_event("FAIL", payload)


def sse_download(zip_name: str) -> str:
    return sse_event("DOWNLOAD", zip_name)


def sse_done() -> str:
    return sse_event("DONE")
