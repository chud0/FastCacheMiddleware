@echo off
setlocal EnableDelayedExpansion

set EXIT_CODE=0
set FAILED_TOOLS=""

echo Run unit-tests...
poetry run pytest ./tests --cov=fast_cache_middleware --cov-report=term-missing --cov-report=html -v
if %ERRORLEVEL% neq 0 (
    echo Tests failed with exit code: %ERRORLEVEL%
    set EXIT_CODE=1
    set FAILED_TOOLS=!FAILED_TOOLS! pytest
)

echo.
if %EXIT_CODE% neq 0 (
    echo ❌ Test execution failed!
    echo Failed tools: %FAILED_TOOLS%
    echo Please check the output above for details.
) else (
    echo ✅ All tests passed successfully!
)

exit /b %EXIT_CODE%
