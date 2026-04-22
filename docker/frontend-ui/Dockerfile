FROM python:3.12-alpine

WORKDIR /app

COPY docker/frontend-ui/server.py /app/server.py
COPY frontend/dist /app/static

ENV FRONTEND_UI_PORT=5173 \
    FRONTEND_PROXY_URL=http://frontend-proxy:8788

EXPOSE 5173

CMD ["python3", "/app/server.py"]
