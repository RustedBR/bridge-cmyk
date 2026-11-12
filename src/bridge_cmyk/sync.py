"""Lógica central — Espresso → arquivo de importação → Mubisys.

FLUXO PRINCIPAL (confirmado 2026-11-12):
1. Busca despesas APROVADAS no Espresso (API sob contrato)
2. Consulta GET /contas-pagar no Mubisys (API pública) p/ deduplicar de
   verdade contra o que JÁ está lançado lá (quando credenciais existem)
3. Filtra: já exportadas (state local) + já no Mubisys + valor inválido
4. GERA ARQUIVO CSV DE IMPORTAÇÃO que o financeiro sobe no painel
   do Mubisys (Financeiro → Contas a Pagar → Importar)
5. Registra no estado local o que foi para o arquivo (anti-duplicata)

A escrita via POST /contas-pagar NÃO existe na API pública do Mubisys
(56 paths parseados, contas-pagar é só GET) — por isso o arquivo de
importação é o mecanismo oficial. Se a Mubisys liberar endpoints de
escrita via contrato, um dia esse módulo ganha um modo direto.
"""
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
    exportadas: int = 0          # foram para o arquivo de importação
    ja_existiam: int = 0         # puladas (estado local ou Mubisys)
    falhas: int = 0              # valor inválido / erro de comunicação
    detalhe: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        return (
            f"📄 {self.exportadas} novas no arquivo  ·  "
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


def _chaves_no_mubisys(cfg: dict) -> set[str]:
    """Chaves externas já lançadas no Mubisys (GET /contas-pagar).

    Usada para dedupe real: não exportar o que o financeiro já lançou
    manualmente. Retorna conjunto de `referencia_externa` encontradas.
    Retorna vazio se a API não estiver configurada/disponível.
    """
    m = cfg.get("mubisys", {})
    if not (m.get("public_key") and m.get("access_token")):
        return set()
    try:
        cliente = MubisysClient(
            m.get("base_url", "https://api.mubisys.com/api"),
            m["public_key"], m["access_token"])
        titulos = cliente.listar_contas_pagar(
            status="TODOS", filtrodata="VENCIMENTO",
            datainicial=(datetime.now() - timedelta(days=90)).date().isoformat(),
            datafinal=datetime.now().date().isoformat())
        chaves = set()
        for t in titulos:
            ref = (t.get("referencia_externa") or t.get("referencia") or "").strip()
            if ref:
                chaves.add(ref)
        log.info("Mubisys: %d títulos consultados, %d com referência externa",
                 len(titulos), len(chaves))
        return chaves
    except (MubisysError, EspressoError) as exc:
        log.warning("Consulta ao Mubisys indisponível (%s) — dedupe via estado local",
                    exc)
        return set()


def gerar_arquivo_importacao(despesas: list[dict], destino) -> list[str]:
    """Gera CSV de importação (fluxo principal).

    Formato genérico UTF-8 BOM + separador ';' (Excel abre direto).
    NOTA: ajustar o cabeçalho ao modelo de importação real do painel
    Mubisys (Financeiro → Contas a Pagar → Importar) quando disponível.
    """
    from pathlib import Path

    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"importacao_mubisys_{datetime.now():%Y-%m-%d}.csv"

    campos = [
        "data_vencimento", "valor", "descricao", "fornecedor",
        "centro_custo", "referencia_externa",
    ]
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        writer.writeheader()
        for d in despesas:
            # despesas já mapeadas (mapear_despesa) ou cruas do Espresso
            escritor = {
                "data_vencimento": (d.get("data_vencimento")
                                    or d.get("due_date") or d.get("date")),
                "valor": f"{d['valor']:.2f}",
                "descricao": (d.get("descricao") or d.get("description") or "")[:120],
                "fornecedor": d.get("fornecedor") or d.get("supplier") or "Diversos",
                "centro_custo": (d.get("centro_custo")
                                 or _categoria_para_centro_custo(
                                     d.get("_cfg", {}), d.get("category", ""))
                                 or "Despesas Gerais"),
                "referencia_externa": f"espresso:{d.get('espresso_id') or d.get('id')}",
            }
            writer.writerow(escritor)
    log.info("Arquivo de importação gerado: %s", caminho)
    return [str(caminho)]


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
                "data_processamento", "espresso_id", "valor", "fornecedor",
                "categoria", "centro_custo", "status", "obs",
            ],
        )
        if novo:
            writer.writeheader()
        writer.writerows(linhas)


def sincronizar(cfg: dict, since: str | None = None, dry_run: bool = False) -> ResultadoSync:
    """Fluxo completo: Espresso → validação/dedupe → arquivo de importação."""
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

    despesas_brutas = espresso.despesas_aprovadas(inicio_filtro)
    log.info("Espresso retornou %d despesas aprovadas", len(despesas_brutas))

    ja_no_mubisys = _chaves_no_mubisys(cfg)
    novas = []
    resultado = ResultadoSync()
    linhas_rel = []

    for d in despesas_brutas:
        eid = str(d["id"])
        ref = f"espresso:{eid}"
        linha = {
            "data_processamento": datetime.now().isoformat(timespec="seconds"),
            "espresso_id": eid,
            "valor": d["value"],
            "fornecedor": d.get("supplier") or "Diversos",
            "categoria": d.get("category", ""),
            "centro_custo": "",
            "status": "",
            "obs": "",
        }

        if state.already_synced(eid) or ref in ja_no_mubisys:
            resultado.ja_existiam += 1
            linha.update(status="ja_existia",
                         obs="pulada (já exportada/registrada)")
            linhas_rel.append(linha)
            log.info("Despesa %s já registrada — pulando", eid)
            continue

        if not d["value"] or d["value"] <= 0:
            resultado.falhas += 1
            linha.update(status="falha", obs="valor inválido (<= 0)")
            linhas_rel.append(linha)
            log.warning("Despesa %s com valor inválido — pulada", eid)
            continue

        despesa = mapear_despesa(cfg, d)
        linha["centro_custo"] = despesa["centro_custo"]
        novas.append(despesa)
        resultado.exportadas += 1
        linha.update(status="nova")
        linhas_rel.append(linha)
        log.info("[OK] %s → R$%.2f (%s) cc=%s",
                 eid, despesa["valor"], despesa["fornecedor"],
                 despesa["centro_custo"])

    if not dry_run and novas:
        destino = config.app_dir() / "importacoes"
        caminhos = gerar_arquivo_importacao(novas, destino)
        for despesa in novas:
            state.mark_synced(
                despesa["espresso_id"], "CSV",
                despesa["valor"], despesa["fornecedor"],
                despesa["data_vencimento"])
        resultado.detalhe.extend(caminhos)
        log.info("Arquivo gerado: %s", caminhos[0])
    elif not dry_run:
        log.info("Nenhuma despesa nova — arquivo não gerado")

    _gravar_relatorio_csv(linhas_rel)
    if not dry_run:
        state.set_last_sync(datetime.now().isoformat())
    log.info("Sync concluído: %s", resultado.resumo())
    return resultado
