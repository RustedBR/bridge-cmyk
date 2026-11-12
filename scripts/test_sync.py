"""Teste offline da lógica de sincronização (sem APIs reais)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Aponta o pacote para src/ e força config app_dir() para um dir temporário
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import bridge_cmyk.config as config  # noqa: E402
from bridge_cmyk import state  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="bridge_test_"))
# Isola config E state em um dir temporário (o teste não toca dados reais)
config.CONFIG_PATH = TMP / "config.json"
state.STATE_DIR = TMP / "data"
state.STATE_DB = state.STATE_DIR / "state.db"

from bridge_cmyk import sync  # noqa: E402


def main() -> None:
    cfg = {
        "mubisys": {"base_url": "https://api.mubisys.com/api",
                    "public_key": "teste", "access_token": "teste"},
        "espresso": {"base_url": "https://espresso.test",
                     "token": "teste"},
        "categoria_map": {"alimentacao": "Alimentacao",
                          "combustivel": "Combustivel"},
        "centro_custo_padrao": "Despesas Gerais",
    }

    # Fake: 3 despesas, uma repetida no meio
    chamadas_mubisys = []

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
                {"id": "1", "value": 150.0, "category": "alimentacao",
                 "supplier": "Fornecedor A", "date": "2026-11-10",
                 "description": "almoço (duplicada)"},
            ]

    class FakeMubisys:
        def criar_contas_pagar(self, titulo):
            chamadas_mubisys.append(titulo)
            return f"T-{len(chamadas_mubisys)}"

    # monkeypatch os clientes no namespace de sync (que é de onde eles vêm)
    sync.EspressoClient = lambda *a, **k: FakeEspresso()
    sync.MubisysClient = lambda *a, **k: FakeMubisys()

    res = sync.sincronizar(cfg)
    print("== RESULTADO ==")
    print(f"lancadas={res.lancadas} ja_existiam={res.ja_existiam} falhas={res.falhas}")
    print("\n== Payloads enviados ao Mubisys ==")
    for p in chamadas_mubisys:
        print(p)
    print(f"\n== state.db: {state.sync_count()} registros ==")

    assert res.lancadas == 2, "esperava 2 lançadas (mapeada + categoria desconhecida -> padrão)"
    assert res.ja_existiam == 1, "esperava 1 duplicada pulada"
    assert res.falhas == 1, "esperava 1 falha (valor 0)"
    assert chamadas_mubisys[0]["centro_custo"] == "Alimentacao"
    assert chamadas_mubisys[0]["referencia_externa"] == "espresso:1"
    assert chamadas_mubisys[1]["centro_custo"] == "Despesas Gerais"
    print("\n✅ TODOS OS ASSERTES PASSARAM (lógica de mapeamento, dedupe e validação OK)")


if __name__ == "__main__":
    main()
