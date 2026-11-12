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
    assert res.dedupe_erp is False, "sem credenciais Mubisys → sem consulta ao ERP"
    assert res.precisa_revisao_duplicata is True, (
        "sem Pro + exportadas → deve avisar para revisar duplicatas")

    # 2ª execução: as 3 já foram exportadas → todas puladas
    res2 = sync.sincronizar(cfg)
    print("\n== RESULTADO 2ª EXECUÇÃO (anti-duplicata local) ==")
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
    print("=== CENÁRIO HÍBRIDO: Mubi Pro ATIVADO (credenciais presentes) ===")


def test_hibrido_com_pro() -> None:
    """Simula a CMYK com Mubi Pro: dedupe contra o Mubisys via API.
    Mesma despesa já lançada lá (ref espresso:9) NÃO pode ser exportada,
    mesmo sem o Bridge ter exportado antes (estado local vazio)."""
    cfg_pro = {
        "mubisys": {"base_url": "https://api.mubisys.com/api",
                    "public_key": "chavepro", "access_token": "tok"},
        "espresso": {"base_url": "https://espresso.test", "token": "teste"},
        "categoria_map": {"alimentacao": "Alimentacao"},
        "centro_custo_padrao": "Despesas Gerais",
    }

    class FakeEspressoPro:
        def despesas_aprovadas(self, since):
            return [
                {"id": "9", "value": 50.0, "category": "alimentacao",
                 "supplier": "Padaria", "date": "2026-11-12",
                 "description": "café"},
                {"id": "10", "value": 75.0, "category": "alimentacao",
                 "supplier": "Lanchonete", "date": "2026-11-12",
                 "description": "almoço"},
            ]

    class FakeMubisysPro:
        def listar_contas_pagar(self, **params):
            # Já existe título com referência externa espresso:9 no ERP
            return [{"referencia_externa": "espresso:9"}]

    sync.EspressoClient = lambda *a, **k: FakeEspressoPro()
    sync.MubisysClient = lambda *a, **k: FakeMubisysPro()

    res = sync.sincronizar(cfg_pro)
    print(res.resumo())
    assert res.exportadas == 1, "só a 10 (a 9 já está no Mubisys)"
    assert res.ja_existiam == 1, "despesa 9 pulada pela consulta ao ERP"
    assert res.dedupe_erp is True, "com credenciais → consultou o ERP"
    assert res.precisa_revisao_duplicata is False, (
        "com Pro + consulta ok → sem aviso de revisão")

    csv_path = Path(res.detalhe[0])
    conteudo = csv_path.read_text(encoding="utf-8-sig")
    assert "espresso:9" not in conteudo, "9 não pode estar no arquivo"
    assert "espresso:10" in conteudo
    print("✅ CENÁRIO HÍBRIDO VALIDADO: sem Pro = dedupe local; com Pro = "
          "dedupe contra o ERP (zero código extra, só credencial no config)")


def make_csv_espresso(caminho: Path) -> None:
    """Monta um CSV exportado do Espresso (separador ;, nomes variados)."""
    conteudo = (
        "Data;Valor;Categoria;Estabelecimento;Descrição;Situação;Nº\n"
        "2026-11-10;150,00;alimentacao;Fornecedor A;almoço;aprovado;1001\n"
        "2026-11-11;220,50;Combustivel;Posto B;combustível;Aprovado;1002\n"
        "2026-11-11;0,00;Transporte;Uber;corrida;aprovado;1003\n"
        "2026-11-11;99,90;Alimentação;Restaurante C;jantar;REJEITADA;1004\n"
        "2026-11-11;33,33;consumo;Loja D;material;aprovado;1005\n"
    )
    caminho.write_text(conteudo, encoding="utf-8-sig")


def test_modo_csv_manual() -> None:
    """Modo A: processa CSV exportado do Espresso SEM nenhuma API."""
    cfg = {
        "mubisys": {"base_url": "https://api.mubisys.com/api",
                    "public_key": "", "access_token": ""},
        "espresso": {"base_url": "", "token": ""},   # SEM APIs configuradas
        "categoria_map": {"alimentacao": "Alimentacao",
                          "consumo": "Consumo"},
        "centro_custo_padrao": "Despesas Gerais",
    }
    from bridge_cmyk import sync as sync_mod

    csv_in = TMP / "espresso_export.csv"
    make_csv_espresso(csv_in)

    # isola state para nova execução
    state.STATE_DB = TMP / "data2" / "state.db"
    state.STATE_DIR = TMP / "data2"

    res = sync_mod.processar_csv_espresso(cfg, str(csv_in))
    print("\n== MODO A (CSV manual, sem APIs) ==")
    print(res.resumo())
    # 1001, 1002, 1005 exportadas; 1003 valor 0 falha; 1004 rejeitada ignorada
    assert res.exportadas == 3, f"esperava 3 exportadas, veio {res.exportadas}"
    assert res.falhas == 1, "esperava 1 falha (valor 0)"
    assert res.ja_existiam == 0, "nada duplicado na 1ª passada"

    conteudo = Path(res.detalhe[0]).read_text(encoding="utf-8-sig")
    assert "espresso:1001" in conteudo
    assert "espresso:1004" not in conteudo, "rejeitada não pode entrar"
    assert "Alimentacao" in conteudo
    print("✅ MODO A VALIDADO: funciona sem API nenhuma (CSV exportado do Espresso)")


if __name__ == "__main__":
    main()
    test_hibrido_com_pro()
    test_modo_csv_manual()
