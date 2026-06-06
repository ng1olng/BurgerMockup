FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ server/

# Inside the container bind all interfaces; the compose port mapping restricts
# exposure to the host's loopback (the server has no auth).
ENV MCP_BIND_HOST=0.0.0.0 MCP_PORT=8100 FILES_DIR=/data/files METRICS_PATH=/data/metrics/metrics.jsonl

HEALTHCHECK --interval=5s --timeout=3s --retries=10 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8100/health')"

CMD ["python", "-m", "server.main"]
