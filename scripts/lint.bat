@echo off
setlocal EnableDelayedExpansion

set EXIT_CODE=0

echo Running black...
poetry run black ./fast_cache_middleware ./examples ./tests --check --diff
if %ERRORLEVEL% neq 0 (
    echo Black failed with exit code %ERRORLEVEL%
    set EXIT_CODE=1
)

echo Running isort...
poetry run isort ./fast_cache_middleware ./examples ./tests --check-only --diff
if %ERRORLEVEL% neq 0 (
    echo isort failed with exit code %ERRORLEVEL%
    set EXIT_CODE=1
)

echo Running mypy...
poetry run mypy ./fast_cache_middleware ./examples ./tests
if %ERRORLEVEL% neq 0 (
    echo mypy failed with exit code %ERRORLEVEL%
    set EXIT_CODE=1
)

exit /b %EXIT_CODE%