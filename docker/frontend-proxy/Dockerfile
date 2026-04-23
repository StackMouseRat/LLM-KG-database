FROM python:3.12-alpine

WORKDIR /app

COPY docker/frontend-proxy/server.py /app/server.py
COPY scripts/run_parallel_generation_pipeline.py /app/scripts/run_parallel_generation_pipeline.py

RUN python3 -m pip install --no-cache-dir jieba \
    && mkdir -p /app/data/frontend_pipeline_runs

ENV FRONTEND_PROXY_PORT=8788 \
    LLM_KG_REPO_ROOT=/app \
    PIPELINE_SCRIPT=/app/scripts/run_parallel_generation_pipeline.py \
    PIPELINE_RUN_DIR=/app/data/frontend_pipeline_runs \
    PIPELINE_DEFAULT_OUTPUT_DIR=/app/data/frontend_pipeline_runs

EXPOSE 8788

CMD ["python3", "/app/server.py"]
