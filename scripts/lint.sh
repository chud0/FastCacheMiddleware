#!/bin/bash

EXIT_CODE=0
FAILED_TOOLS=""

echo "Running black..."
poetry run black ./fast_cache_middleware ./examples ./tests --check --diff
if [ $? -ne 0 ]; then
    echo "Black failed with exit code $?"
    EXIT_CODE=1
    FAILED_TOOLS="$FAILED_TOOLS black"
fi

echo "Running isort..."
poetry run isort ./fast_cache_middleware ./examples ./tests --check-only --diff
if [ $? -ne 0 ]; then
    echo "isort failed with exit code $?"
    EXIT_CODE=1
    FAILED_TOOLS="$FAILED_TOOLS isort"
fi

echo "Running mypy..."
poetry run mypy ./fast_cache_middleware ./examples ./tests
if [ $? -ne 0 ]; then
    echo "mypy failed with exit code $?"
    EXIT_CODE=1
    FAILED_TOOLS="$FAILED_TOOLS mypy"
fi

echo
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Linting failed!"
    echo "Failed tools: $FAILED_TOOLS"
    echo "Please check the output above for details."
else
    echo "✅ All linting checks passed successfully!"
fi

exit $EXIT_CODE
