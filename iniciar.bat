@echo off
setlocal EnableDelayedExpansion
title CAD Tools

echo.
echo ==================================================
echo   CAD Tools - Launcher
echo ==================================================
echo.

:: --- 1. VERIFICAR PYTHON ---
set PYTHON_CMD=

python --version >nul 2>&1
if %errorlevel% == 0 ( set PYTHON_CMD=python & goto :check_version )

python3 --version >nul 2>&1
if %errorlevel% == 0 ( set PYTHON_CMD=python3 & goto :check_version )

py --version >nul 2>&1
if %errorlevel% == 0 ( set PYTHON_CMD=py & goto :check_version )

echo [ERRO] Python nao encontrado no PATH.
echo        Instale Python 3.10+ em https://www.python.org/downloads/
echo        e marque "Add Python to PATH" durante a instalacao.
echo.
pause
exit /b 1

:check_version
for /f "tokens=2 delims= " %%v in ('%PYTHON_CMD% --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python: %PYTHON_CMD% %PY_VER%

for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 goto :bad_version
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 10 goto :bad_version
goto :check_reqs

:bad_version
echo [ERRO] Python 3.10 ou superior necessario. Encontrado: %PY_VER%
pause
exit /b 1

:: --- 2. VERIFICAR requirements.txt ---
:check_reqs
if not exist requirements.txt (
    echo [ERRO] requirements.txt nao encontrado.
    echo        Execute este script na pasta raiz do projeto.
    pause
    exit /b 1
)

:: --- 3. VERIFICAR / CRIAR .venv ---
if exist ".venv\Scripts\python.exe" (
    echo [OK] Ambiente virtual .venv ja existe.
) else (
    echo [INFO] Criando ambiente virtual .venv ...
    %PYTHON_CMD% -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERRO] Falha ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo [OK] Ambiente virtual criado.
)

:: --- 4. ATIVAR .venv ---
call ".venv\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao ativar o ambiente virtual.
    pause
    exit /b 1
)
echo [OK] Ambiente virtual ativado.

:: --- 5. ATUALIZAR pip ---
echo [INFO] Atualizando pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip ok.

:: --- 6. INSTALAR PACOTES ---
echo [INFO] Instalando/verificando pacotes...
python -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    echo        Verifique sua conexao com a internet.
    pause
    exit /b 1
)
echo [OK] Pacotes instalados.

:: --- 7. VERIFICAR app.py ---
if not exist app.py (
    echo [ERRO] app.py nao encontrado.
    echo        Execute este script na pasta raiz do projeto.
    pause
    exit /b 1
)

:: --- 8. INICIAR ---
echo.
echo ==================================================
echo   Iniciando CAD Tools...
echo   Pressione CTRL+C para encerrar.
echo ==================================================
echo.

python app.py

echo.
echo [INFO] CAD Tools encerrado.
pause
endlocal
