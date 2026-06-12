# resources-mcp

A [FastMCP](https://gofastmcp.com) server that exposes files from a mounted data directory as MCP resources, with search tools for text files and PDFs. Designed to run in Docker so agents can browse, read, and search your documents over the Model Context Protocol.

Published image: [`jamiewannenburg/resources-mcp`](https://hub.docker.com/r/jamiewannenburg/resources-mcp) on Docker Hub.

## What it provides

**Resources**

- `resource://data` — JSON listing of all files under the data directory (path and size)
- `data://files/{path}` — read or download any file by relative path

Files are registered at startup. Text-like files are returned as UTF-8 strings; binary files are returned as bytes.

**Tools**

- `grep` — search file contents with [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`)
- `pdfgrep` — search PDF text with [pdfgrep](https://pdfgrep.org)

All paths are constrained to the data directory; path traversal is rejected.

## Quick start

1. Put files you want to expose in a `data/` directory next to `docker-compose.yml`:

   ```bash
   mkdir -p data
   cp ~/Documents/*.pdf data/
   ```

2. Start the server (using the published image):

   ```bash
   docker run --rm -p 8000:8000 -v "$(pwd)/data:/data:ro" jamiewannenburg/resources-mcp:latest
   ```

   Or build locally with Compose:

   ```bash
   docker compose up --build
   ```

3. Connect an MCP client to the streamable HTTP endpoint:

   ```
   http://localhost:8000/mcp
   ```

The default compose file mounts `./data` read-only at `/data` inside the container.

## Docker

Pre-built image: [hub.docker.com/r/jamiewannenburg/resources-mcp](https://hub.docker.com/r/jamiewannenburg/resources-mcp)

### Pull and run

```bash
docker pull jamiewannenburg/resources-mcp:latest
docker run --rm -p 8000:8000 -v "$(pwd)/data:/data:ro" jamiewannenburg/resources-mcp:latest
```

### Run with Compose (published image)

```yaml
services:
  resources-mcp:
    image: jamiewannenburg/resources-mcp:latest
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data:ro
    restart: unless-stopped
```

### Build and run with Compose

```bash
docker compose up --build -d
```

### Build and run manually

```bash
docker build -t resources-mcp .
docker run --rm -p 8000:8000 -v "$(pwd)/data:/data:ro" resources-mcp
```

### Mount a different directory

```yaml
# docker-compose.yml
volumes:
  - /path/to/your/files:/data:ro
```

## Configuration

### Application settings

| Variable     | Default | Description                                      |
| ------------ | ------- | ------------------------------------------------ |
| `DATA_DIR`   | `/data` | Directory whose files are exposed as resources   |
| `RECURSIVE`  | `true`  | Include subdirectories when listing and indexing |
| `NAMESPACE`  | *(none)* | Prefix tools and resource URIs to avoid name clashes when multiple MCP servers are combined |

### FastMCP settings

FastMCP reads configuration from `FASTMCP_*` environment variables. Set these in `docker-compose.yml`, the Dockerfile, or at runtime.

| Variable                         | Default            | Description                                      |
| -------------------------------- | ------------------ | ------------------------------------------------ |
| `FASTMCP_HOST`                   | `0.0.0.0`          | Bind address (passed to uvicorn)                 |
| `FASTMCP_PORT`                   | `8000`             | Listen port (passed to uvicorn)                  |
| `FASTMCP_TRANSPORT`            | `streamable-http`  | HTTP transport (`http`, `streamable-http`, `sse`) |
| `FASTMCP_STREAMABLE_HTTP_PATH`   | `/mcp`             | MCP HTTP endpoint path                           |
| `FASTMCP_LOG_LEVEL`              | `INFO`             | Log level (`DEBUG`, `INFO`, `WARNING`, …)        |
| `FASTMCP_JSON_RESPONSE`          | `false`            | Use JSON response format                         |
| `FASTMCP_STATELESS_HTTP`         | `false`            | Stateless HTTP mode                              |
| `FASTMCP_DEBUG`                  | `false`            | Enable debug mode                                |

Example override in Compose:

```yaml
environment:
  DATA_DIR: /data
  RECURSIVE: "true"
  FASTMCP_HOST: "0.0.0.0"
  FASTMCP_PORT: "8000"
  FASTMCP_LOG_LEVEL: "DEBUG"
```

`FASTMCP_HOST` and `FASTMCP_PORT` control where uvicorn listens. Other `FASTMCP_*` variables are read when the ASGI app is created at import time.

### Namespacing (avoiding name clashes)

When this server is used alongside others that expose generic names like `grep`, set a namespace so tools and resources are prefixed. FastMCP has no `FASTMCP_*` setting for this; the server uses FastMCP's built-in [`Namespace`](https://gofastmcp.com/servers/transforms/namespace) transform.

| With `NAMESPACE=nas` | Exposed name / URI |
| -------------------- | ------------------ |
| Tool `grep`          | `nas_grep`         |
| Tool `pdfgrep`       | `nas_pdfgrep`      |
| Resource listing     | `resource://nas/data` |
| File resource        | `data://nas/files/{path}` |

Set via environment variable (works with Docker / uvicorn):

```bash
export NAMESPACE=nas
```

Or when running `python server.py` directly:

```bash
python server.py --namespace nas
```

## Connecting MCP clients

### Cursor

Add to your MCP configuration (Settings → MCP, or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "resources": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Adjust the host and port if you changed `FASTMCP_HOST` / `FASTMCP_PORT` or run the container on a remote host.

## Local development

Without Docker, you need Python 3.12+, [ripgrep](https://github.com/BurntSushi/ripgrep), and [pdfgrep](https://pdfgrep.org) installed on your system.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

export DATA_DIR=./data
export FASTMCP_HOST=127.0.0.1
export FASTMCP_TRANSPORT=streamable-http

python server.py
```

Or run uvicorn directly:

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Architecture

```
┌─────────────┐     streamable-http      ┌──────────────────┐
│  MCP client │ ◄──────────────────────► │  uvicorn         │
│  (Cursor)   │     /mcp                 │  server:app      │
└─────────────┘                          └────────┬─────────┘
                                                  │
                                         ┌────────▼─────────┐
                                         │  FastMCP         │
                                         │  - resources     │
                                         │  - grep/pdfgrep  │
                                         └────────┬─────────┘
                                                  │
                                         ┌────────▼─────────┐
                                         │  /data (mounted) │
                                         └──────────────────┘
```

The server runs [uvicorn](https://www.uvicorn.org) against a Starlette ASGI app produced by `mcp.http_app()`. File resources are registered once at startup from the contents of `DATA_DIR`.

## License

See repository license file if present.
