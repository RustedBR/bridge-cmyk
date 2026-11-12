@echo off
REM ============================================================
REM  Build Bridge CMYK — gera BridgeCMYK.exe (onefile) + setup
REM  Requisitos: Python 3.10+ instalado no Windows (python no PATH)
REM  Uso:  duplo clique em build.bat  (ou rodar no cmd)
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0.."
echo.
echo  ============================================
echo   BRIDGE CMYK - BUILD AUTOMATICO (WINDOWS)
echo  ============================================
echo.

REM ---------- 1. Python disponivel? ----------
where python >nul 2>nul
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado no PATH.
    echo  Instale em: https://www.python.org/downloads/
    echo  IMPORTANTE: marque "Add python.exe to PATH" na instalacao.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] %PYVER%

REM ---------- 2. venv ----------
if not exist ".venv" (
    echo  [..] Criando ambiente virtual (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERRO] Falha ao criar venv.
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat

REM ---------- 3. dependencias ----------
echo  [..] Instalando pyinstaller...
pip install --quiet --upgrade pip pyinstaller
if errorlevel 1 (
    echo  [ERRO] Falha ao instalar pyinstaller.
    pause
    exit /b 1
)

REM ---------- 4. build do .exe ----------
echo  [..] Compilando BridgeCMYK.exe (leva ~1 min)...
pyinstaller --noconfirm --onefile --windowed ^
    --name BridgeCMYK ^
    --add-data "src;src" ^
    src\main.py
if errorlevel 1 (
    echo  [ERRO] PyInstaller falhou.
    pause
    exit /b 1
)

REM ---------- 5. empacotar arquivos de apoio ----------
echo  [..] Copiando config.example.json e LEIA-ME.txt...
copy /y config.example.json dist\config.json >nul
copy /y LEIA-ME.txt dist\LEIA-ME.txt >nul

echo.
echo  ============================================
echo   BUILD CONCLUIDO!
echo.
echo   Gerado em:  dist\BridgeCMYK.exe
echo   Acompanhantes: dist\config.json (credenciais)
echo                  dist\LEIA-ME.txt
echo.
echo   Para criar o INSTALADOR (opcional):
echo     - instale o Inno Setup 6: https://jrsoftware.org/isinfo.php
echo     - e rode:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" scripts\bridgecmyk_setup.iss
echo  ============================================
pause
