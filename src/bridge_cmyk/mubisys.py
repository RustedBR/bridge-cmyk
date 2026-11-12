"""Cliente da API do Mubisys — Contas a Pagar.

Base: https://api.mubisys.com/docs (OpenAPI 1.1.0 — VERIFICADO em 2026-11-12)
Auth: header `Access-Token` + `publicKey` no path.
403 = cliente não possui pacote Mubi Pro (API exige plano Pro).

⚠️ LIMITAÇÃO CONFIRMADA NA DOC PÚBLICA (56 paths parseados):
   - contas-pagar: apenas GET (listar, listar por id) e provisões GET.
   - NÃO EXISTE POST/PUT para criar ou alterar títulos a pagar na API
     pública. Os únicos POSTs são de cadastro: cliente, fornecedor,
     funil de vendas (9 POSTs no total, nenhum financeiro).
   → Para CRIAR títulos é preciso verificar com a Mubisys se há API de
     escrita via contrato/Mubi Pro (indocumentada) OU usar importação
     por arquivo no painel (o conector gera planilha/CSV de importação).
"""
from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

log = logging.getLogger("bridge.mubisys")


class MubisysError(Exception):
    """Falha de comunicação ou autenticação com o Mubisys."""


class MubisysClient:
    def __init__(self, base_url: str, public_key: str, token: str,
                 timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.public_key = public_key
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}/{self.public_key}{path}"
        headers = {"Access-Token": self.token}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as r:
                body = r.read()
                return json.loads(body) if body else {}
        except HTTPError as e:
            if e.code == 403:
                raise MubisysError(
                    "Mubisys retornou 403 — a API exige o pacote Mubi Pro "
                    "(contatar a Mubisys para habilitar)."
                ) from e
            if e.code in (401, 422):
                raise MubisysError(
                    f"Mubisys HTTP {e.code} em {path}: {e.reason}"
                ) from e
            raise MubisysError(f"Mubisys HTTP {e.code} em {path}") from e
        except URLError as e:
            raise MubisysError(f"Mubisys sem conexão ({e.reason})") from e

    def listar_contas_pagar(self, **params) -> list[dict]:
        """GET /contas-pagar — consulta (única via pública confirmada).

        Parâmetros obrigatórios na doc: status (TODOS/PENDENTE/VENCIDO/PAGO),
        filtrodata (EMISSAO/VENCIMENTO/PAGAMENTO), datainicial, datafinal.
        """
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        resp = self._request("GET", f"/contas-pagar?{qs}" if qs else "/contas-pagar")
        return resp.get("data") or resp.get("contas") or []

    # ------------------------------------------------------------------
    # ESCRITA: não documentada na API pública.
    # Se a Mubisys confirmar endpoints de criação (contrato/Mubi Pro),
    # implementar aqui com o payload real deles. Enquanto isso, o conector
    # gera ARQUIVO DE IMPORTAÇÃO (ver sync.gerar_arquivo_importacao).
    # ------------------------------------------------------------------
