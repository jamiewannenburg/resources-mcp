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
ENV RECURSIVE=true
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000
ENV FASTMCP_TRANSPORT=streamable-http

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn server:app --host \"$FASTMCP_HOST\" --port \"$FASTMCP_PORT\""]
