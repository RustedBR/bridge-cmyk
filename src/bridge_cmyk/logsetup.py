"""Log para arquivo diário (logs/bridge_YYYY-MM-DD.log, retém 30 dias)."""
from __future__ import annotations

import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

from . import config


def setup_logging(console_level: int = logging.DEBUG) -> Path:
    """Configura log em logs/bridge_YYYY-MM-DD.log. Retorna o caminho."""
    pasta = config.app_dir() / "logs"
    pasta.mkdir(exist_ok=True)

    arquivo = pasta / f"bridge_{datetime.now():%Y-%m-%d}.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(arquivo, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(console_level)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(fh)
    root.addHandler(ch)

    _limpar_logs_antigos(pasta)
    return arquivo


def _limpar_logs_antigos(pasta: Path, dias: int = 30) -> None:
    ontem = datetime.now().timestamp() - dias * 86400
    for f in pasta.glob("bridge_*.log"):
        try:
            if f.stat().st_mtime < ontem:
                f.unlink()
        except OSError:
            pass
