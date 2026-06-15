FROM python:3.12-slim

WORKDIR /app

RUN mkdir -p /data

COPY pyproject.toml README.md ./
COPY qa_annotate/ qa_annotate/
COPY scripts/ scripts/
COPY seed/demo.sql seed/demo.sql
COPY seed/llm-analysis-2026-06-15_zh.md seed/llm-analysis-2026-06-15_zh.md
COPY seed/llm-analysis-2026-06-15_en.md seed/llm-analysis-2026-06-15_en.md

RUN pip install --no-cache-dir .

ENV DB_DIR=/data
ENV ENVIRONMENT=production
ENV SECRET_KEY=qaloop-demo-jwt-secret-key-32bytes
ENV PYTHONUNBUFFERED=1

RUN chmod +x scripts/space_entrypoint.sh

EXPOSE 7860

CMD ["sh", "scripts/space_entrypoint.sh"]
