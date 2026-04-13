FROM python:3.12-alpine

RUN apk add --no-cache docker-cli

WORKDIR /app

COPY scripts/nebula_http_gateway.py /app/nebula_http_gateway.py

EXPOSE 8787

CMD ["python", "/app/nebula_http_gateway.py", "--host", "0.0.0.0", "--port", "8787", "--docker-network", "nebula-docker-compose_nebula-net", "--nebula-host", "graphd", "--nebula-port", "9669", "--nebula-user", "root", "--nebula-password", "nebula"]
