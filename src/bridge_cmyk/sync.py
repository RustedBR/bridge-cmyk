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
    dedupe_erp: bool = False     # True = consultou o Mubisys (Mubi Pro)
    detalhe: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        return (
            f"📄 {self.exportadas} novas no arquivo  ·  "
            f"⏭️ {self.ja_existiam} já existiam  ·  "
            f"⚠️ {self.falhas} falhas"
        )

    @property
    def precisa_revisao_duplicata(self) -> bool:
        """Sem Mubi Pro (dedupe só local) + algo exportado → revisar."""
        return (not self.dedupe_erp) and self.exportadas > 0


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


def _chaves_no_mubisys(cfg: dict) -> tuple[set[str], bool]:
    """Chaves externas já lançadas no Mubisys (GET /contas-pagar).

    Retorna (conjunto de referências, consultou_erp):
    - consultou_erp=False quando não há credenciais Mubisys (sem Pro) ou a
      consulta falhou → dedupe fica só no estado local.
    """
    m = cfg.get("mubisys", {})
    if not (m.get("public_key") and m.get("access_token")):
        log.info("Mubisys sem credenciais — dedupe apenas local (Mubi Pro opcional)")
        return set(), False
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
        return chaves, True
    except (MubisysError, EspressoError) as exc:
        log.warning("Consulta ao Mubisys indisponível (%s) — dedupe via estado local",
                    exc)
        return set(), False


def _normalizar_coluna(nome: str) -> str:
    """Normaliza nomes de coluna do export do Espresso p/ chaves canônicas."""
    n = (nome or "").strip().lower()
    n = n.replace(" ", "_").replace("-", "_").replace("ã", "a").replace("ç", "c")
    n = n.replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    n = n.replace("è", "e").replace("à", "a").replace("ô", "o").replace("õ", "o")
    mapeamentos = {
        "id": "id",
        "codigo": "id",
        "nº": "id",
        "data": "date",
        "data_da_despesa": "date",
        "data_lancamento": "date",
        "competencia": "date",
        "valor": "value",
        "valor_total": "value",
        "amount": "value",
        "categoria": "category",
        "tipo": "category",
        "classificacao": "category",
        "fornecedor": "supplier",
        "estabelecimento": "supplier",
        "nome_do_fornecedor": "supplier",
        "descricao": "description",
        "descricao_da_despesa": "description",
        "observacoes": "description",
        "observacao": "description",
        "motivo": "description",
        "centro_de_custo": "cost_center",
        "centro_custo": "cost_center",
        "status": "status",
        "situacao": "status",
    }
    return mapeamentos.get(n, n)


def ler_csv_espresso(caminho: str) -> list[dict]:
    """Lê o arquivo exportado pelo Espresso (CSV/planilha) e devolve
    despesas no formato canônico {id, date, value, category, supplier,
    description, cost_center, status}.

    Aceita separador ';' ou ',' (detecta pelo cabeçalho) e nomes de coluna
    variados (Data, Valor, Categoria, Fornecedor, Descrição, Status...).
    """
    from pathlib import Path

    caminho = Path(caminho)
    if not caminho.exists():
        raise EspressoError(f"Arquivo não encontrado: {caminho}")

    if caminho.suffix.lower() == ".xlsx":
        raise EspressoError(
            "Formato .xlsx detectado — exporte do Espresso como CSV "
            "(ou salve a planilha como CSV).")

    with open(caminho, encoding="utf-8-sig", errors="replace") as f:
        conteudo = f.read()

    # detecta separador pela primeira linha
    primeira = conteudo.splitlines()[0] if conteudo.splitlines() else ""
    sep = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.DictReader(
        conteudo.splitlines(), delimiter=sep)

    campos = [c.strip() for c in (leitor.fieldnames or [])]
    mapa = {c: _normalizar_coluna(c) for c in campos}

    despesas = []
    for lin in leitor:
        if not any((v or "").strip() for v in lin.values()):
            continue  # linha em branco
        item = {}
        for nome_col, chave in mapa.items():
            item[chave] = (lin.get(nome_col) or "").strip()
        # ignora linhas não-aprovadas se a coluna existir
        status = item.get("status", "")
        if status and status.lower() not in ("", "aprovado", "aprovada",
                                             "approved", "pago", "paga"):
            continue
        valor = item.get("value", "0").replace(".", "").replace(",", ".")
        try:
            valor_f = float(valor) if valor else 0.0
        except ValueError:
            valor_f = 0.0
        despesas.append({
            "id": item.get("id") or item.get("date", ""),
            "date": item.get("date") or item.get("id"),
            "value": valor_f,
            "category": item.get("category", ""),
            "supplier": item.get("supplier", ""),
            "description": item.get("description", ""),
            "cost_center": item.get("cost_center", ""),
            "status": item.get("status", ""),
        })
    log.info("CSV Espresso: %d despesas lidas de %s", len(despesas), caminho)
    return despesas


def processar_csv_espresso(cfg: dict, caminho_csv: str) -> ResultadoSync:
    """Fluxo 100% por arquivo (SEM APIs): lê export do Espresso → valida →
    dedupe local → gera CSV de importação do Mubisys."""
    resultado = ResultadoSync()
    linhas_rel = []
    novas = []

    despesas_brutas = ler_csv_espresso(caminho_csv)
    log.info("Processando %d despesas do arquivo %s",
             len(despesas_brutas), caminho_csv)

    for d in despesas_brutas:
        eid = str(d["id"])
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

        if state.already_synced(eid):
            resultado.ja_existiam += 1
            linha.update(status="ja_existia",
                         obs="pulada (já exportada)")
            linhas_rel.append(linha)
            log.info("Despesa %s já exportada — pulando", eid)
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

    if novas:
        destino = config.app_dir() / "importacoes"
        caminhos = gerar_arquivo_importacao(novas, destino)
        for despesa in novas:
            state.mark_synced(
                despesa["espresso_id"], "CSV",
                despesa["valor"], despesa["fornecedor"],
                despesa["data_vencimento"])
        resultado.detalhe.extend(caminhos)
        log.info("Arquivo gerado: %s", caminhos[0])

    _gravar_relatorio_csv(linhas_rel)
    state.set_last_sync(datetime.now().isoformat())
    log.info("Processamento por CSV concluído: %s", resultado.resumo())
    return resultado


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

    resultado = ResultadoSync()
    ja_no_mubisys, consultou_erp = _chaves_no_mubisys(cfg)
    resultado.dedupe_erp = consultou_erp
    novas = []
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
