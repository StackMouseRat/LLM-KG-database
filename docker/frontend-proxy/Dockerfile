FROM python:3.12-alpine

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY docker/frontend-proxy/server.py /app/server.py
COPY scripts/run_parallel_generation_pipeline.py /app/scripts/run_parallel_generation_pipeline.py

RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install jieba \
    && mkdir -p /app/data/frontend_pipeline_runs

ENV FRONTEND_PROXY_PORT=8788 \
    LLM_KG_REPO_ROOT=/app \
    PIPELINE_SCRIPT=/app/scripts/run_parallel_generation_pipeline.py \
    PIPELINE_RUN_DIR=/app/data/frontend_pipeline_runs \
    PIPELINE_DEFAULT_OUTPUT_DIR=/app/data/frontend_pipeline_runs

EXPOSE 8788

CMD ["python3", "/app/server.py"]
