#!/bin/bash

EXIT_CODE=0

echo "Runing tests..."
poetry run pytest ./tests --cov=fast_cache_middleware --cov-report=term-missing --cov-report=html -v
if [ $? -ne 0 ]; then
    echo "Eror test run with code: $?"
    EXIT_CODE=1
fi

exit $EXIT_CODE
