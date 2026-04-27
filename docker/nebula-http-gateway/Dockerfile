FROM python:3.12-alpine

RUN apk add --no-cache docker-cli
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple nebula3-python==3.8.3

WORKDIR /app

COPY scripts/nebula_http_gateway.py /app/nebula_http_gateway.py

EXPOSE 8787

CMD ["python", "/app/nebula_http_gateway.py", "--host", "0.0.0.0", "--port", "8787", "--docker-network", "nebula-docker-compose_nebula-net", "--nebula-host", "graphd", "--nebula-port", "9669", "--nebula-user", "root", "--nebula-password", "nebula"]
