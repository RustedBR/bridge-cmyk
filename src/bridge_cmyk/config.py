"""Config carregada/salva em config.json, ao lado do executável."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Diretório do executável (funciona em .exe empacotado e em dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


CONFIG_PATH = app_dir() / "config.json"

DEFAULTS: dict = {
    "mubisys": {
        "base_url": "https://api.mubisys.com/api",
        "public_key": "",
        "access_token": "",
    },
    "espresso": {
        "base_url": "",
        "token": "",
    },
    "categoria_map": {
        "alimentacao": "Alimentacao",
        "combustivel": "Combustivel",
        "transporte": "Transporte",
        "hospedagem": "Hospedagem",
        "material_escritorio": "Material de Escritorio",
        "manutencao": "Manutencao",
    },
    "centro_custo_padrao": "Despesas Gerais",
}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = json.loads(json.dumps(base))
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return _deep_merge(DEFAULTS, json.load(f))
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(DEFAULTS))
    return json.loads(json.dumps(DEFAULTS))


def save_config(cfg: dict) -> None:
    merged = _deep_merge(DEFAULTS, cfg)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)


def is_configured(cfg: dict) -> bool:
    """Config OK = Espresso configurado (Mubisys é OPCIONAL: seu GET serve
    só para dedupe; o fluxo principal gera arquivo de importação)."""
    e = cfg.get("espresso", {})
    return bool(e.get("base_url") and e.get("token"))


def missing_items(cfg: dict) -> list[str]:
    faltam = []
    e = cfg.get("espresso", {})
    if not e.get("base_url"):
        faltam.append("Espresso host (base_url)")
    if not e.get("token"):
        faltam.append("Espresso token")
    return faltam


def criar_config_se_ausente() -> None:
    if not CONFIG_PATH.exists():
        save_config(DEFAULTS)
        os.makedirs(app_dir() / "logs", exist_ok=True)
