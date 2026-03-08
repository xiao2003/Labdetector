from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    kwargs: dict[str, Any] = {}
    creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    if creationflags:
        kwargs["creationflags"] = creationflags
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def run_hidden(*popenargs: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    base = hidden_subprocess_kwargs()
    base.update(kwargs)
    return subprocess.run(*popenargs, **base)


def popen_hidden(*popenargs: Any, **kwargs: Any) -> subprocess.Popen:
    base = hidden_subprocess_kwargs()
    base.update(kwargs)
    return subprocess.Popen(*popenargs, **base)