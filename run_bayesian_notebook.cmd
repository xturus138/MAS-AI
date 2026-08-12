@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%venv\Scripts\python.exe"
set "NOTEBOOK_PATH=%PROJECT_ROOT%experiment\bayesian\bayesian_dummy_closed_loop.ipynb"
set "MODE=%~1"
set "CHECK_ONLY=0"

if /I "%MODE%"=="" set "MODE=full"
if /I "%MODE%"=="help" goto :help
if /I "%MODE%"=="-h" goto :help
if /I "%MODE%"=="/?" goto :help

if /I "%MODE%"=="check" (
    set "MODE=full"
    set "CHECK_ONLY=1"
) else if /I "%MODE%"=="full" (
    rem The full experiment runs One-Hot, TF-IDF, and E5 embeddings.
) else if /I "%MODE%"=="fast" (
    rem The quick experiment skips the E5 model download and embedding run.
) else (
    echo Unknown mode: %~1
    echo Run "%~nx0 help" for usage.
    exit /b 2
)

if not exist "%PYTHON%" (
    echo Python virtual environment was not found:
    echo %PYTHON%
    echo Create or restore the project's venv, then run this file again.
    exit /b 1
)

pushd "%PROJECT_ROOT%" || (
    echo Could not open the project directory.
    exit /b 1
)

if not exist "%NOTEBOOK_PATH%" (
    echo Notebook was not found:
    echo %NOTEBOOK_PATH%
    popd
    exit /b 1
)

"%PYTHON%" -m jupyter lab --version >nul 2>&1
if errorlevel 1 (
    echo JupyterLab is not installed in this virtual environment.
    echo Run: "%PYTHON%" -m pip install jupyterlab ipywidgets
    popd
    exit /b 1
)

set "PYTHONIOENCODING=utf-8"
if /I "%MODE%"=="fast" (
    set "BAYESIAN_NOTEBOOK_RUN_E5=0"
) else (
    set "BAYESIAN_NOTEBOOK_RUN_E5=1"
)

if "%CHECK_ONLY%"=="1" (
    echo Ready to run the Bayesian notebook.
    echo Mode: %MODE%
    echo E5 enabled: %BAYESIAN_NOTEBOOK_RUN_E5%
    echo Notebook: %NOTEBOOK_PATH%
    popd
    exit /b 0
)

echo Starting JupyterLab for the Bayesian notebook...
echo Mode: %MODE%
echo E5 enabled: %BAYESIAN_NOTEBOOK_RUN_E5%
echo Close JupyterLab or press Ctrl+C in this window when you are finished.
"%PYTHON%" -m jupyter lab "%NOTEBOOK_PATH%"
set "EXIT_CODE=%ERRORLEVEL%"

popd
if not "%EXIT_CODE%"=="0" (
    echo JupyterLab stopped with exit code %EXIT_CODE%.
)
exit /b %EXIT_CODE%

:help
echo Usage: %~nx0 [full^|fast^|check^|help]
echo.
echo   full   Open JupyterLab and run all notebook methods, including E5. Default.
echo   fast   Open JupyterLab with BAYESIAN_NOTEBOOK_RUN_E5=0 for One-Hot and TF-IDF only.
echo   check  Verify Python, JupyterLab, and the notebook path without starting JupyterLab.
echo   help   Show this message.
exit /b 0
