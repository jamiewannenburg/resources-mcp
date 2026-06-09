FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep pdfgrep \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py search_tools.py .

RUN mkdir -p /data

ENV DATA_DIR=/data
ENV MCP_TRANSPORT=streamable-http
ENV HOST=0.0.0.0
ENV PORT=8000
ENV RECURSIVE=true

EXPOSE 8000

CMD ["python", "server.py"]
