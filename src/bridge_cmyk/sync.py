"""Lógica central da sincronização Espresso → Mubisys."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import config, state
from .espresso import EspressoClient, EspressoError
from .mubisys import MubisysClient, MubisysError

log = logging.getLogger("bridge.sync")


@dataclass
class ResultadoSync:
    lancadas: int = 0
    ja_existiam: int = 0
    falhas: int = 0
    detalhe: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        return (
            f"✅ {self.lancadas} lançadas  ·  "
            f"⏭️ {self.ja_existiam} já existiam  ·  "
            f"⚠️ {self.falhas} falhas"
        )


def _categoria_para_centro_custo(cfg: dict, categoria: str) -> str:
    mapa = cfg.get("categoria_map", {}) or {}
    chave = (categoria or "").strip().lower()
    return mapa.get(chave, cfg.get("centro_custo_padrao", "Despesas Gerais"))


def mapear_despesa(cfg: dict, d: dict) -> dict:
    return {
        "espresso_id": d["id"],
        "valor": d["value"],
        "descricao": (d.get("description") or "")[:120],
        "fornecedor": d.get("supplier") or "Diversos",
        "data_vencimento": d.get("due_date") or d.get("date"),
        "centro_custo": _categoria_para_centro_custo(cfg, d.get("category", "")),
    }


def _payload_mubisys(despesa: dict) -> dict:
    """Corpo do POST /contas-pagar (ajustar ao OpenAPI real)."""
    return {
        "valor": despesa["valor"],
        "descricao": despesa["descricao"],
        "fornecedor": despesa["fornecedor"],
        "data_vencimento": despesa["data_vencimento"],
        "centro_custo": despesa["centro_custo"],
        "referencia_externa": f"espresso:{despesa['espresso_id']}",
    }


def _gravar_relatorio_csv(linhas: list[dict]) -> None:
    """Grava uma linha por despesa processada em logs/relatorio_<data>.csv."""
    if not linhas:
        return
    pasta_logs = config.app_dir() / "logs"
    pasta_logs.mkdir(exist_ok=True)
    arquivo = pasta_logs / f"relatorio_{datetime.now():%Y-%m-%d}.csv"
    novo = not arquivo.exists()
    with open(arquivo, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "data_envio", "espresso_id", "valor", "fornecedor",
                "categoria", "centro_custo", "status", "mubisys_id", "obs",
            ],
        )
        if novo:
            writer.writeheader()
        writer.writerows(linhas)


def sincronizar(cfg: dict, since: str | None = None, dry_run: bool = False) -> ResultadoSync:
    """Fluxo completo de uma sincronização. Retorna resumo."""
    if not config.is_configured(cfg):
        faltam = config.missing_items(cfg)
        raise EspressoError("Configuração incompleta — faltam: " + ", ".join(faltam))

    inicio_filtro = (
        since
        or state.last_sync()
        or (datetime.now() - timedelta(days=7)).date().isoformat()
    )
    log.info("Sync iniciado (desde %s, dry_run=%s)", inicio_filtro, dry_run)

    espresso = EspressoClient(
        cfg["espresso"]["base_url"], cfg["espresso"]["token"]
    )
    mubisys = MubisysClient(
        cfg["mubisys"]["base_url"],
        cfg["mubisys"]["public_key"],
        cfg["mubisys"]["access_token"],
    )

    despesas = espresso.despesas_aprovadas(inicio_filtro)
    log.info("Espresso retornou %d despesas aprovadas", len(despesas))

    resultado = ResultadoSync()
    linhas_rel = []

    for d in despesas:
        eid = d["id"]
        linha = {
            "data_envio": datetime.now().isoformat(timespec="seconds"),
            "espresso_id": eid,
            "valor": d["value"],
            "fornecedor": d.get("supplier") or "Diversos",
            "categoria": d.get("category", ""),
            "centro_custo": "",
            "status": "",
            "mubisys_id": "",
            "obs": "",
        }

        if state.already_synced(eid):
            resultado.ja_existiam += 1
            linha.update(status="ja_existia", obs="pulada (anti-duplicata)")
            linhas_rel.append(linha)
            log.info("Despesa %s já sincronizada — pulando", eid)
            continue

        if not d["value"] or d["value"] <= 0:
            resultado.falhas += 1
            linha.update(status="falha", obs="valor inválido (<= 0)")
            linhas_rel.append(linha)
            log.warning("Despesa %s com valor inválido — pulada", eid)
            continue

        despesa = mapear_despesa(cfg, d)
        linha["centro_custo"] = despesa["centro_custo"]

        if dry_run:
            resultado.lancadas += 1
            linha.update(status="dry_run", obs="não enviada (dry-run)")
            linhas_rel.append(linha)
            log.info("[DRY] lançaria %s → R$%.2f (%s) cc=%s",
                     eid, despesa["valor"], despesa["fornecedor"],
                     despesa["centro_custo"])
            continue

        try:
            mid = mubisys.criar_contas_pagar(_payload_mubisys(despesa))
            state.mark_synced(eid, mid, despesa["valor"],
                              despesa["fornecedor"], despesa["data_vencimento"])
            resultado.lancadas += 1
            linha.update(status="lancada", mubisys_id=mid)
            linhas_rel.append(linha)
            log.info("Despesa %s lançada no Mubisys (id=%s, R$%.2f)",
                     eid, mid, despesa["valor"])
        except (MubisysError, EspressoError) as exc:
            resultado.falhas += 1
            linha.update(status="falha", obs=str(exc)[:150])
            linhas_rel.append(linha)
            log.error("Falha ao lançar despesa %s: %s", eid, exc)

    _gravar_relatorio_csv(linhas_rel)
    if not dry_run:
        state.set_last_sync(datetime.now().isoformat())
    log.info("Sync concluído: %s", resultado.resumo())
    return resultado
