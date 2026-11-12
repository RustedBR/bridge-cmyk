"""Bridge CMYK — Espresso → Mubisys.

Uso:
  BridgeCMYK.exe            abre a interface gráfica
  BridgeCMYK.exe --auto     roda uma sincronização sem janela (agendador)
"""
from __future__ import annotations

import sys


def _auto() -> int:
    """Modo silencioso p/ agendador: sincroniza e loga resultado."""
    from bridge_cmyk import config, logsetup, sync

    config.criar_config_se_ausente()
    arquivo_log = logsetup.setup_logging(console_level=__import__("logging").WARNING)

    cfg = config.load_config()
    if not config.is_configured(cfg):
        print(f"[BridgeCMYK] Configuração incompleta — veja {arquivo_log}")
        return 2
    try:
        res = sync.sincronizar(cfg)
        print(f"[BridgeCMYK] {res.resumo()}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[BridgeCMYK] Erro: {exc}")
        return 1


def main() -> int:
    if "--auto" in sys.argv[1:]:
        return _auto()
    from bridge_cmyk.app import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
