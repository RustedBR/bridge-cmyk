"""Cliente da API do Mubisys — criação de Contas a Pagar.

Base: https://api.mubisys.com/docs (OpenAPI 1.1.0)
Auth: header `Access-Token` + `publicKey` no path.
403 = cliente não possui pacote Mubi Pro (API exige plano Pro).
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

    def criar_contas_pagar(self, titulo: dict) -> str:
        """Cria um título a pagar. Retorna o id do título criado.

        TODO: ajustar o payload exato ao contrato real (campos obrigatórios
        do POST /{publicKey}/contas-pagar no OpenAPI da Mubisys).
        """
        resp = self._request("POST", "/contas-pagar", titulo)
        return str(
            resp.get("id")
            or resp.get("titulo", {}).get("id")
            or resp.get("data", {}).get("id")
            or "?"
        )
