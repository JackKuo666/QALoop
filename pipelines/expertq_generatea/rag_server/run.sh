#!/bin/bash
# Bio RAG Server startup script

echo "Starting Bio RAG Server (using Biopython Entrez - no ES required)..."
echo ""

cd "$(dirname "$0")"
export PYTHONPATH="$PWD:$PYTHONPATH"

# Check .env
if [ -f ".env" ]; then
    echo "Using .env configuration"
fi

echo "Endpoints:"
echo "  - Health: http://localhost:9487/health"
echo "  - Retrieve: POST http://localhost:9487/retrieve"
echo ""

python3 main.py
