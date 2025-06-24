#!/bin/bash

EXIT_CODE=0
FAILED_TOOLS=""

echo "Running tests..."
poetry run pytest ./tests --cov=fast_cache_middleware --cov-report=term-missing --cov-report=html -v
if [ $? -ne 0 ]; then
    echo "Tests failed with exit code: $?"
    EXIT_CODE=1
    FAILED_TOOLS="$FAILED_TOOLS pytest"
fi

echo
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Test execution failed!"
    echo "Failed tools: $FAILED_TOOLS"
    echo "Please check the output above for details."
else
    echo "✅ All tests passed successfully!"
fi

exit $EXIT_CODE
