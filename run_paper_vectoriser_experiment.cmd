@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%venv\Scripts\python.exe"
set "NOTEBOOK_PATH=%PROJECT_ROOT%experiment\bayesian\three_method_representation_comparison.ipynb"
set "MODE=%~1"
set "CHECK_ONLY=0"

if /I "%MODE%"=="" set "MODE=full"
if /I "%MODE%"=="help" goto :help
if /I "%MODE%"=="-h" goto :help
if /I "%MODE%"=="/?" goto :help

if /I "%MODE%"=="check" (
    set "MODE=full"
    set "CHECK_ONLY=1"
) else if /I not "%MODE%"=="full" (
    echo Unknown mode: %~1
    echo Run "%~nx0 help" for usage.
    exit /b 2
)

if not exist "%PYTHON%" (
    echo Python virtual environment was not found:
    echo %PYTHON%
    exit /b 1
)

if not exist "%NOTEBOOK_PATH%" (
    echo Notebook was not found:
    echo %NOTEBOOK_PATH%
    exit /b 1
)

pushd "%PROJECT_ROOT%" || exit /b 1
"%PYTHON%" -m jupyter lab --version >nul 2>&1
if errorlevel 1 (
    echo JupyterLab is not installed in this virtual environment.
    popd
    exit /b 1
)

set "PYTHONIOENCODING=utf-8"
set "PAPER_VECTORISER_RUN_FULL=1"

if "%CHECK_ONLY%"=="1" (
    echo Ready to run the seven-vectoriser experiment.
    echo The first full run needs Internet to cache Word2Vec, GloVe, FastText, ELMo, and Flair.
    echo Later runs reuse the local model caches.
    popd
    exit /b 0
)

echo Starting JupyterLab for the seven-vectoriser experiment...
echo The first full run downloads missing pretrained model weights.
echo Close JupyterLab or press Ctrl+C in this window when you are finished.
"%PYTHON%" -m jupyter lab "%NOTEBOOK_PATH%"
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:help
echo Usage: %~nx0 [full^|check^|help]
echo.
echo   full   Open JupyterLab for all seven vectorisers. Default.
echo   check  Verify the local environment without starting JupyterLab.
echo   help   Show this message.
exit /b 0
