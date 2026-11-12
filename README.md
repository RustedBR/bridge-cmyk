# Bridge CMYK — Espresso → Mubisys

Programa Windows com interface gráfica que sincroniza **despesas aprovadas do
Espresso** como **títulos de Contas a Pagar no Mubisys** via API REST.

Roda na máquina do usuário (financeiro da CMYK). **Não depende de servidor
externo nem de cronjob no PC do desenvolvedor.**

---

## O que o programa faz (fluxo)

1. **Configuração (1ª vez)** — usuário abre a aba *Configuração*, preenche:
   - Mubisys: `publicKey` + `Access-Token`
   - Espresso: host + token da API
   - Mapeamento categoria Espresso → centro de custo Mubisys
   - Salva em `config.json` (fica ao lado do .exe)
2. **Sincronizar** — usuário clica em *Sincronizar agora*:
   - Conecta no Espresso e busca despesas **aprovadas** desde o último sync
   - Mapeia a categoria de cada despesa para o centro de custo do Mubisys
   - **Anti-duplicata**: consulta o banco local (`data/state.db`) e pula o que já foi enviado
   - Cria um título de Contas a Pagar no Mubisys por despesa (via `POST /contas-pagar`)
   - Registra cada envio no banco local com a referência externa `espresso:<id>`
   - Mostra resumo na tela: lançadas ✓, já existiam ⏭️, falhas ⚠️
3. **Logs** — tudo é gravado em:
   - `logs/bridge_YYYY-MM-DD.log` (diário, retém 30 dias)
   - `logs/relatorio_YYYY-MM-DD.csv` (uma linha por despesa processada)

## Como executar

**Opção A — Instalador (usuário não-técnico):**
1. Rode `BridgeCMYKSetup.exe`
2. Siga o assistente (próximo → próximo → instalar)
3. Abra o programa pelo atalho do menu Iniciar
4. Preencha a aba *Configuração* (credenciais vêm do financeiro)
5. Clique *Sincronizar agora*

**Opção B — Portátil (sem instalar):**
1. Descompacte `BridgeCMYK-win64.zip`
2. Abra `BridgeCMYK.exe` (config.json é criado ao lado)

Para agendar sozinho na máquina do usuário:
`Agendador de Tarefas` → criar tarefa → programa `BridgeCMYK.exe` com
argumento `--auto` (roda sem abrir janela e loga silenciosamente).

## Como gerar o .exe (no Windows, uma vez)

```bat
:: opcional: criar venv
py -m venv .venv
.venv\Scripts\activate
pip install pyinstaller

pyinstaller --noconfirm --onefile --windowed --name BridgeCMYK ^
  --add-data "src;src" src\main.py
```

Saída: `dist/BridgeCMYK.exe`. Empacote com o `scripts/bridgecmyk_setup.iss`
(Inno Setup) para o instalador, ou zip a pasta.

## Estrutura

```
bridge-cmyk/
├── src/
│   ├── main.py          # entrada
│   └── bridge_cmyk/
│       ├── app.py       # GUI (Tkinter)
│       ├── config.py    # carrega/salva config.json
│       ├── espresso.py  # cliente da API do Espresso
│       ├── mubisys.py   # cliente da API do Mubisys
│       ├── sync.py      # lógica da sincronização
│       └── state.py     # banco local (anti-duplicata + última sync)
├── scripts/
│   └── bridgecmyk_setup.iss   # script do instalador (Inno Setup)
└── config.example.json
```

## Configuração (config.json)

```json
{
  "mubisys": {
    "base_url": "https://api.mubisys.com/api",
    "public_key": "",
    "access_token": ""
  },
  "espresso": {
    "base_url": "",
    "token": ""
  },
  "categoria_map": {
    "alimentacao": "Alimentacao",
    "combustivel": "Combustivel",
    "transporte": "Transporte"
  },
  "centro_custo_padrao": "Despesas Gerais"
}
```

Credenciais nunca ficam no código — só no config.json local da máquina.
