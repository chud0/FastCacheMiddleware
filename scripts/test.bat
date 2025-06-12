@echo off
setlocal EnableDelayedExpansion

set EXIT_CODE=0

echo Запуск тестов...
poetry run pytest ./tests --cov=fast_cache_middleware --cov-report=term-missing -v
if %ERRORLEVEL% neq 0 (
    echo Тесты завершились с ошибкой, код: %ERRORLEVEL%
    set EXIT_CODE=1
)

exit /b %EXIT_CODE%
