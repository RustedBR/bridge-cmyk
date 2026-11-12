"""Cliente da API do Espresso — despesas aprovadas.

O contrato exato (paths/headers/response) precisa ser confirmado com o
Espresso. Este módulo centraliza TODAS as chamadas para facilitar o ajuste.
"""
from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

log = logging.getLogger("bridge.espresso")


class EspressoError(Exception):
    """Falha de comunicação ou autenticação com o Espresso."""


class EspressoClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        req = Request(url, headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except HTTPError as e:
            raise EspressoError(
                f"Espresso HTTP {e.code} em {path}: {e.reason}"
            ) from e
        except URLError as e:
            raise EspressoError(f"Espresso sem conexão ({e.reason})") from e

    def despesas_aprovadas(self, since: str) -> list[dict]:
        """Despesas aprovadas desde `since` (YYYY-MM-DD).

        TODO: ajustar path/params ao contrato real da API do Espresso.
        Forma assumida: GET /expenses?status=approved&since=YYYY-MM-DD
        retornando {"data": [ {...}, ... ]} com campos:
          id, date, value, category, supplier, description, cost_center
        """
        data = self._get(f"/expenses?status=approved&since={since}")
        items = data.get("data") or data.get("expenses") or []
        out = []
        for it in items:
            out.append(
                {
                    "id": str(it.get("id") or it.get("expense_id")),
                    "date": it.get("date") or it.get("expense_date"),
                    "value": float(it.get("value") or it.get("amount") or 0),
                    "category": (it.get("category") or it.get("type") or ""),
                    "supplier": (it.get("supplier") or it.get("vendor") or ""),
                    "description": (
                        it.get("description")
                        or it.get("reason")
                        or it.get("note")
                        or ""
                    ),
                    "due_date": it.get("due_date") or it.get("date"),
                }
            )
        return out
