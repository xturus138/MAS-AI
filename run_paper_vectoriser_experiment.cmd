@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%venv\Scripts\python.exe"
set "NOTEBOOK_PATH=%PROJECT_ROOT%experiment\bayesian\three_method_representation_comparison.ipynb"
set "MODE=%~1"
set "CHECK_ONLY=0"
set "PAPER_VECTORISER_MODE=quick"

if /I "%MODE%"=="" set "MODE=quick"
if /I "%MODE%"=="help" goto :help
if /I "%MODE%"=="-h" goto :help
if /I "%MODE%"=="/?" goto :help

if /I "%MODE%"=="check" (
    set "MODE=quick"
    set "CHECK_ONLY=1"
) else if /I "%MODE%"=="quick" (
    set "PAPER_VECTORISER_MODE=quick"
) else if /I "%MODE%"=="all" (
    set "PAPER_VECTORISER_MODE=all"
) else if /I "%MODE%"=="full" (
    set "PAPER_VECTORISER_MODE=all"
) else if /I "%MODE%"=="TF-IDF" (
    set "PAPER_VECTORISER_MODE=TF-IDF"
) else if /I "%MODE%"=="Feature Hashing" (
    set "PAPER_VECTORISER_MODE=Feature Hashing"
) else if /I "%MODE%"=="Word2Vec" (
    set "PAPER_VECTORISER_MODE=Word2Vec"
) else if /I "%MODE%"=="GloVe" (
    set "PAPER_VECTORISER_MODE=GloVe"
) else if /I "%MODE%"=="FastText" (
    set "PAPER_VECTORISER_MODE=FastText"
) else if /I "%MODE%"=="ELMo" (
    set "PAPER_VECTORISER_MODE=ELMo"
) else if /I "%MODE%"=="Flair" (
    set "PAPER_VECTORISER_MODE=Flair"
) else (
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

if "%CHECK_ONLY%"=="1" (
    echo Mode: quick ^(TF-IDF, Feature Hashing^)
    echo Ready to run without pretrained-model downloads.
    popd
    exit /b 0
)

echo Starting JupyterLab for the selected vectorisers: %PAPER_VECTORISER_MODE%
if /I "%PAPER_VECTORISER_MODE%"=="all" echo Warning: all downloads the five pretrained vectoriser weights and can take substantial time and disk space.
if /I "%PAPER_VECTORISER_MODE%"=="all" echo Use Ctrl+C now if you did not mean to run all seven methods.
echo Close JupyterLab or press Ctrl+C in this window when you are finished.
"%PYTHON%" -m jupyter lab "%NOTEBOOK_PATH%"
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:help
echo Usage: %~nx0 [quick^|all^|TF-IDF^|"Feature Hashing"^|Word2Vec^|GloVe^|FastText^|ELMo^|Flair^|check^|help]
echo.
echo   quick  Open TF-IDF and Feature Hashing only. Default and no pretrained downloads.
echo   all    Open all seven vectorisers. This may download several gigabytes of model weights.
echo   METHOD Open one named vectoriser, for example: %~nx0 Word2Vec
echo   check  Verify the quick local environment without starting JupyterLab.
echo   help   Show this message.
exit /b 0
