@echo off
setlocal EnableDelayedExpansion

set EXIT_CODE=0
set FAILED_TOOLS=""

echo Running black...
poetry run black ./fast_cache_middleware ./examples ./tests --check --diff
if %ERRORLEVEL% neq 0 (
    echo Black failed with exit code %ERRORLEVEL%
    set EXIT_CODE=1
    set FAILED_TOOLS=!FAILED_TOOLS! black
)

echo Running isort...
poetry run isort ./fast_cache_middleware ./examples ./tests --check-only --diff
if %ERRORLEVEL% neq 0 (
    echo isort failed with exit code %ERRORLEVEL%
    set EXIT_CODE=1
    set FAILED_TOOLS=!FAILED_TOOLS! isort
)

echo Running mypy...
poetry run mypy ./fast_cache_middleware ./examples ./tests
if %ERRORLEVEL% neq 0 (
    echo mypy failed with exit code %ERRORLEVEL%
    set EXIT_CODE=1
    set FAILED_TOOLS=!FAILED_TOOLS! mypy
)

echo.
if %EXIT_CODE% neq 0 (
    echo ❌ Linting failed!
    echo Failed tools: %FAILED_TOOLS%
    echo Please check the output above for details.
) else (
    echo ✅ All linting checks passed successfully!
)

exit /b %EXIT_CODE%