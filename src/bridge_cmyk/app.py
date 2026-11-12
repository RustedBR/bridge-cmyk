"""Interface gráfica (Tkinter) — abas Configuração e Sincronização."""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import config, sync
from .sync import ResultadoSync

log = logging.getLogger("bridge.app")


class BridgeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bridge CMYK — Espresso → Mubisys")
        self.geometry("760x540")
        self.minsize(680, 480)

        cfg = config.load_config()
        self.vars: dict[str, tk.StringVar] = {}
        for chave in (
            "mubisys_base_url", "mubisys_public_key", "mubisys_token",
            "espresso_base_url", "espresso_token",
        ):
            self.vars[chave] = tk.StringVar()
        self.vars["mubisys_base_url"].set(cfg["mubisys"]["base_url"])
        self.vars["mubisys_public_key"].set(cfg["mubisys"]["public_key"])
        self.vars["mubisys_token"].set(cfg["mubisys"]["access_token"])
        self.vars["espresso_base_url"].set(cfg["espresso"]["base_url"])
        self.vars["espresso_token"].set(cfg["espresso"]["token"])

        self._build_ui()
        self._atualizar_status_config()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._aba_config(nb)
        self._aba_sync(nb)

    def _aba_config(self, nb: ttk.Notebook) -> None:
        aba = ttk.Frame(nb, padding=12)
        nb.add(aba, text="⚙️  Configuração")

        ttk.Label(aba, text="MUBISYS (ERP)", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        campos = [
            ("mubisys_base_url",    "URL da API (base)"),
            ("mubisys_public_key",  "publicKey"),
            ("mubisys_token",       "Access-Token"),
        ]
        for i, (var, rotulo) in enumerate(campos, start=1):
            ttk.Label(aba, text=rotulo).grid(row=i, column=0, sticky="w", pady=3)
            campo = ttk.Entry(aba, textvariable=self.vars[var], width=70)
            if "token" in var or "key" in var:
                campo.configure(show="•")
            campo.grid(row=i, column=1, sticky="we", pady=3, padx=(8, 0))

        ttk.Label(aba, text="ESPRESSO (despesas)", font=("Segoe UI", 10, "bold")).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(14, 4))
        campos = [
            ("espresso_base_url", "URL da API (host)"),
            ("espresso_token",    "Token de acesso"),
        ]
        for j, (var, rotulo) in enumerate(campos, start=6):
            ttk.Label(aba, text=rotulo).grid(row=j, column=0, sticky="w", pady=3)
            campo = ttk.Entry(aba, textvariable=self.vars[var], width=70)
            if "token" in var:
                campo.configure(show="•")
            campo.grid(row=j, column=1, sticky="we", pady=3, padx=(8, 0))

        self.status_config = tk.StringVar(value="")
        ttk.Label(aba, textvariable=self.status_config, foreground="#666").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(10, 0))

        ttk.Button(aba, text="💾 Salvar configuração", command=self._salvar_config).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(aba, text="📁 Abrir pasta de logs",
                   command=lambda: self._abrir_pasta(config.app_dir() / "logs")).grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(6, 0))

        aba.columnconfigure(1, weight=1)

    def _aba_sync(self, nb: ttk.Notebook) -> None:
        aba = ttk.Frame(nb, padding=12)
        nb.add(aba, text="🔁  Sincronizar")

        lbl_titulo = ttk.Label(
            aba, text="Escolha como entrar as despesas do Espresso:",
            font=("Segoe UI", 10, "bold"))
        lbl_titulo.pack(anchor="w")

        # Modo 1: CSV manual (funciona SEM nenhuma API)
        frame1 = ttk.LabelFrame(aba, text="Modo A — Arquivo do Espresso (sem API)",
                                padding=8)
        frame1.pack(fill="x", pady=(8, 0))
        ttk.Label(
            frame1,
            text=("Exporte as despesas do Espresso como CSV/Excel e selecione "
                  "o arquivo.\nFunciona sem configurar nenhuma API."),
            wraplength=640, justify="left").pack(anchor="w")
        self.btn_csv = ttk.Button(frame1, text="📂 Selecionar arquivo do Espresso",
                                  command=self._rodar_csv)
        self.btn_csv.pack(anchor="w", pady=(6, 0))

        # Modo 2: API (quando as credenciais forem preenchidas)
        frame2 = ttk.LabelFrame(aba, text="Modo B — Via API do Espresso",
                                padding=8)
        frame2.pack(fill="x", pady=(8, 0))
        ttk.Label(
            frame2,
            text=("Busca as despesas aprovadas direto na API. Requer host + "
                  "token preenchidos na aba Configuração."),
            wraplength=640, justify="left").pack(anchor="w")
        barra = ttk.Frame(frame2)
        barra.pack(fill="x", pady=(6, 0))
        self.btn_sync = ttk.Button(barra, text="▶  Buscar via API",
                                   command=self._rodar_sync)
        self.btn_sync.pack(side="left")
        self.btn_abrir_csv = ttk.Button(barra, text="📂 Abrir CSV",
                                        state="disabled",
                                        command=self._abrir_ultimo_csv)
        self.btn_abrir_csv.pack(side="left", padx=(10, 0))
        self.lbl_resumo = ttk.Label(barra, text="", foreground="#1a7f37")
        self.lbl_resumo.pack(side="left", padx=16)

        self.txt_log = tk.Text(aba, height=16, state="disabled",
                               font=("Consolas", 9), wrap="word")
        self.txt_log.pack(fill="both", expand=True, pady=(10, 0))
        self.txt_log.tag_configure("erro", foreground="#c0392b")
        self.txt_log.tag_configure("ok", foreground="#1a7f37")

    # ------------------------------------------------------------- ações
    def _salvar_config(self) -> None:
        cfg = config.load_config()
        cfg["mubisys"]["base_url"] = self.vars["mubisys_base_url"].get().strip()
        cfg["mubisys"]["public_key"] = self.vars["mubisys_public_key"].get().strip()
        cfg["mubisys"]["access_token"] = self.vars["mubisys_token"].get().strip()
        cfg["espresso"]["base_url"] = self.vars["espresso_base_url"].get().strip()
        cfg["espresso"]["token"] = self.vars["espresso_token"].get().strip()
        config.save_config(cfg)
        self._atualizar_status_config()
        messagebox.showinfo("Bridge CMYK", "Configuração salva em config.json")

    def _atualizar_status_config(self) -> None:
        cfg = config.load_config()
        if config.is_configured(cfg):
            msg = "✅ Configuração completa — pronto para gerar o arquivo"
            if not (cfg.get("mubisys", {}).get("public_key")
                    and cfg.get("mubisys", {}).get("access_token")):
                msg += "  (Mubisys opcional: só para checar duplicatas)"
            self.status_config.set(msg)
        else:
            faltam = config.missing_items(cfg)
            self.status_config.set("⚠️  Falta: " + ", ".join(faltam))

    def _rodar_sync(self) -> None:
        cfg = config.load_config()
        if not config.is_configured(cfg):
            faltam = config.missing_items(cfg)
            messagebox.showwarning("Bridge CMYK",
                                   "Configuração incompleta. Faltam:\n- " +
                                   "\n- ".join(faltam))
            return
        self.btn_sync.configure(state="disabled")
        self.btn_abrir_csv.configure(state="disabled")
        self._ultimo_csv: str | None = None
        self.lbl_resumo.configure(text="sincronizando…")
        threading.Thread(target=self._sync_worker, args=(cfg,), daemon=True).start()

    def _rodar_csv(self) -> None:
        from tkinter import filedialog

        caminho = filedialog.askopenfilename(
            title="Selecionar arquivo exportado do Espresso",
            filetypes=[("CSV / planilha", "*.csv *.xlsx"),
                       ("CSV", "*.csv"),
                       ("Todos os arquivos", "*.*")])
        if not caminho:
            return
        cfg = config.load_config()
        self.btn_csv.configure(state="disabled")
        self._ultimo_csv: str | None = None
        self.lbl_resumo.configure(text="processando arquivo…")
        threading.Thread(
            target=self._csv_worker, args=(cfg, caminho), daemon=True).start()

    def _csv_worker(self, cfg: dict, caminho: str) -> None:
        try:
            resultado = sync.processar_csv_espresso(cfg, caminho)
            self.after(0, self._sync_done, resultado, None)
        except Exception as exc:  # noqa: BLE001 — mostra qualquer erro na tela
            log.error("Falha ao processar CSV: %s", exc)
            self.after(0, self._sync_done, None, exc)

    def _sync_worker(self, cfg: dict) -> None:
        try:
            resultado = sync.sincronizar(cfg)
            self.after(0, self._sync_done, resultado, None)
        except Exception as exc:  # noqa: BLE001 — mostra qualquer erro na tela
            log.error("Falha geral no sync: %s", exc)
            self.after(0, self._sync_done, None, exc)

    def _sync_done(self, resultado: ResultadoSync | None, erro: Exception | None) -> None:
        self.btn_sync.configure(state="normal")
        self.btn_csv.configure(state="normal")
        if erro:
            self.lbl_resumo.configure(text="❌ erro", foreground="#c0392b")
            self._log_linha(f"ERRO: {erro}", tag="erro")
        else:
            self.lbl_resumo.configure(text=resultado.resumo(), foreground="#1a7f37")
            self._log_linha("\n" + resultado.resumo(), tag="ok")
            if resultado.detalhe:
                self._ultimo_csv = resultado.detalhe[0]
                self._log_linha(f"📄 Arquivo gerado: {resultado.detalhe[0]}", tag="ok")
                self._log_linha(
                    "→ Importe no Mubisys: Financeiro › Contas a Pagar › Importar")
                if resultado.precisa_revisao_duplicata:
                    self._log_linha(
                        "⚠️  Sem Mubi Pro: o programa não consegue checar o que já "
                        "foi lançado no Mubisys.", tag="erro")
                    self._log_linha(
                        "    ANTES de importar, confira no Mubisys se essas despesas "
                        "não já foram lançadas manualmente.", tag="erro")
                    self._log_linha(
                        "    📌 Botão abaixo abre o arquivo para conferir.", tag="erro")
                    self.btn_abrir_csv.configure(state="normal")

    _def = None

    def _log_linha(self, texto: str, tag: str = "") -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", texto + "\n", tag)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _abrir_ultimo_csv(self) -> None:
        caminho = getattr(self, "_ultimo_csv", None)
        if caminho:
            self._abrir_pasta(config.app_dir() / "importacoes")

    @staticmethod
    def _abrir_pasta(pasta) -> None:
        import os
        import subprocess
        import sys

        pasta.mkdir(exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(pasta))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(pasta)])


def main() -> None:
    config.criar_config_se_ausente()
    from . import logsetup

    arquivo_log = logsetup.setup_logging(console_level=logging.WARNING)
    log.info("Bridge CMYK iniciado (log: %s)", arquivo_log)
    app = BridgeApp()
    app.mainloop()
