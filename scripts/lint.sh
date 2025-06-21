#!/bin/bash

EXIT_CODE=0

echo "Running black..."
poetry run black ./fast_cache_middleware ./examples ./tests --check --diff
if [ $? -ne 0 ]; then
    echo "Black failed with exit code $?"
    EXIT_CODE=1
fi

echo "Running isort..."
poetry run isort ./fast_cache_middleware ./examples ./tests --check-only --diff
if [ $? -ne 0 ]; then
    echo "isort failed with exit code $?"
    EXIT_CODE=1
fi

echo "Running mypy..."
poetry run mypy ./fast_cache_middleware ./examples ./tests
if [ $? -ne 0 ]; then
    echo "mypy failed with exit code $?"
    EXIT_CODE=1
fi

exit $EXIT_CODE
