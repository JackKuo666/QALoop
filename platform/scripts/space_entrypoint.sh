#!/bin/sh
set -e

python scripts/space_init.py
exec uvicorn qa_annotate.main:app --host 0.0.0.0 --port "${PORT:-7860}"
