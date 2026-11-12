"""Teste offline da lógica de sincronização (sem APIs reais).

Valida o FLUXO PRINCIPAL: Espresso → dedupe → arquivo CSV de importação.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Aponta o pacote para src/ e isola config/state em dir temporário
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import bridge_cmyk.config as config  # noqa: E402
from bridge_cmyk import state  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="bridge_test_"))
config.CONFIG_PATH = TMP / "config.json"
state.STATE_DIR = TMP / "data"
state.STATE_DB = state.STATE_DIR / "state.db"
config.app_dir = lambda: TMP  # type: ignore[assignment]  # noqa: SLF001

from bridge_cmyk import sync  # noqa: E402


def main() -> None:
    cfg = {
        "mubisys": {"base_url": "https://api.mubisys.com/api",
                    "public_key": "", "access_token": ""},
        "espresso": {"base_url": "https://espresso.test",
                     "token": "teste"},
        "categoria_map": {"alimentacao": "Alimentacao",
                          "combustivel": "Combustivel"},
        "centro_custo_padrao": "Despesas Gerais",
    }

    class FakeEspresso:
        def despesas_aprovadas(self, since):
            return [
                {"id": "1", "value": 150.0, "category": "alimentacao",
                 "supplier": "Fornecedor A", "date": "2026-11-10",
                 "description": "almoço"},
                {"id": "2", "value": 220.5, "category": "desconhecida",
                 "supplier": "Posto B", "date": "2026-11-11",
                 "description": "combustível"},
                {"id": "3", "value": 0, "category": "transporte",
                 "supplier": "Uber", "date": "2026-11-11",
                 "description": "corrida"},
                {"id": "4", "value": 99.9, "category": "alimentacao",
                 "supplier": "Restaurante C", "date": "2026-11-11",
                 "description": "jantar"},
            ]

    sync.EspressoClient = lambda *a, **k: FakeEspresso()

    res = sync.sincronizar(cfg)
    print("== RESULTADO 1ª EXECUÇÃO ==")
    print(res.resumo())
    print("arquivos:", res.detalhe)

    assert res.exportadas == 3, "esperava 3 exportadas (1, 2, 4)"
    assert res.ja_existiam == 0, "nenhuma duplicada na 1ª execução"
    assert res.falhas == 1, "esperava 1 falha (valor 0)"

    # 2ª execução: as 3 já foram exportadas → todas puladas
    res2 = sync.sincronizar(cfg)
    print("\n== RESULTADO 2ª EXECUÇÃO (anti-duplicata) ==")
    print(res2.resumo())
    assert res2.exportadas == 0, "nada novo na 2ª execução"
    assert res2.ja_existiam == 3, "3 já exportadas puladas"

    # Valida conteúdo do CSV gerado
    csv_path = Path(res.detalhe[0])
    linhas = csv_path.read_text(encoding="utf-8-sig").strip().splitlines()
    print("\n== CSV ==")
    print("\n".join(linhas))
    assert linhas[0] == (
        "data_vencimento;valor;descricao;fornecedor;centro_custo;referencia_externa"
    )
    assert "espresso:1" in linhas[1]
    assert "Alimentacao" in linhas[1]

    print("\n✅ TODOS OS ASSERTES PASSARAM (fluxo principal: CSV de importação)")


if __name__ == "__main__":
    main()
