# resources-mcp

A [FastMCP](https://gofastmcp.com) server that exposes files from a mounted data directory as MCP resources, with search tools for text files and PDFs. Designed to run in Docker so agents can browse, read, and search your documents over the Model Context Protocol.

Published image: [`jamiewannenburg/resource-mcp`](https://hub.docker.com/r/jamiewannenburg/resource-mcp) on Docker Hub.

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
   docker run --rm -p 8000:8000 -v "$(pwd)/data:/data:ro" jamiewannenburg/resource-mcp:latest
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

Pre-built image: [hub.docker.com/r/jamiewannenburg/resource-mcp](https://hub.docker.com/r/jamiewannenburg/resource-mcp)

### Pull and run

```bash
docker pull jamiewannenburg/resource-mcp:latest
docker run --rm -p 8000:8000 -v "$(pwd)/data:/data:ro" jamiewannenburg/resource-mcp:latest
```

### Run with Compose (published image)

```yaml
services:
  resources-mcp:
    image: jamiewannenburg/resource-mcp:latest
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

## Deploy to Google Cloud Run

Cloud Run can run the published Docker image and mount a Cloud Storage bucket at
`/data`, which is the default `DATA_DIR` used by this server. Cloud Run mounts
Cloud Storage buckets with Cloud Storage FUSE, so the mounted bucket appears as a
filesystem path inside the container.

### Prerequisites

1. Install and authenticate the Google Cloud CLI:

   ```bash
   gcloud auth login
   gcloud config set project PROJECT_ID
   ```

2. Enable the required APIs:

   ```bash
   gcloud services enable run.googleapis.com storage.googleapis.com iamcredentials.googleapis.com
   ```

3. Create or choose a bucket that contains the files to expose:

   ```bash
   gcloud storage buckets create gs://BUCKET_NAME --location=REGION
   gcloud storage cp --recursive ./data/* gs://BUCKET_NAME/
   ```

4. Choose a service account for Cloud Run:

   Cloud Run runs as a **service identity** (a service account). Set
   `SA_EMAIL` to the account the service will use.

   **Option A: Dedicated service account (recommended)** — least privilege; only
   the roles you grant in step 5:

   ```bash
   gcloud iam service-accounts create resources-mcp \
     --display-name="resources-mcp Cloud Run"

   SA_EMAIL="resources-mcp@PROJECT_ID.iam.gserviceaccount.com"
   ```

   Pass this account to Cloud Run with `--service-account="${SA_EMAIL}"`. Your
   deployer identity needs `roles/iam.serviceAccountUser` on `${SA_EMAIL}`.

   **Option B: Default Compute Engine service account** — Cloud Run uses this
   identity when you omit `--service-account`. Fewer setup steps, but that
   account may already have broad project access:

   ```bash
   PROJECT_NUMBER="$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')"

   SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
   ```

5. Grant the service account the permissions it needs:

   **Read the mounted bucket** — required for the Cloud Storage volume mount and
   for signed download links:

   ```bash
   gcloud storage buckets add-iam-policy-binding gs://BUCKET_NAME \
     --member="serviceAccount:${SA_EMAIL}" \
     --role="roles/storage.objectViewer"
   ```

   **Sign download URLs** — required when `SIGNED_URL_SERVICE_ACCOUNT_EMAIL` is
   set. Use the same account for Cloud Run and signing (recommended):

   ```bash
   gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
     --member="serviceAccount:${SA_EMAIL}" \
     --role="roles/iam.serviceAccountTokenCreator"
   ```

   If a different account signs URLs, grant `roles/iam.serviceAccountTokenCreator`
   on that signing account to `${SA_EMAIL}` instead. The signing account also
   needs `roles/storage.objectViewer` on the bucket.

### Deploy the published image

```bash
gcloud run deploy resources-mcp \
  --image docker.io/jamiewannenburg/resource-mcp:latest \
  --region REGION \
  --port 8000 \
  --service-account="${SA_EMAIL}" \
  --set-env-vars DATA_DIR=/data,RECURSIVE=true,SIGNED_URL_BUCKET=BUCKET_NAME,SIGNED_URL_SERVICE_ACCOUNT_EMAIL=${SA_EMAIL} \
  --add-volume mount-path=/data,type=cloud-storage,bucket=BUCKET_NAME,readonly=true
```

If you chose the default Compute Engine service account (Option B), omit
`--service-account`.

By default, keep the service private and grant invoke access only to the callers
that need it. If you intentionally want a public endpoint, add
`--allow-unauthenticated`.

After deployment, connect your MCP client to:

```text
https://SERVICE_URL/mcp
```

You can get the service URL with:

```bash
gcloud run services describe resources-mcp \
  --region REGION \
  --format='value(status.url)'
```

### Build and deploy your local source

If you changed the code and want Cloud Run to build the local Dockerfile:

```bash
gcloud run deploy resources-mcp \
  --source . \
  --region REGION \
  --port 8000 \
  --service-account="${SA_EMAIL}" \
  --set-env-vars DATA_DIR=/data,RECURSIVE=true,SIGNED_URL_BUCKET=BUCKET_NAME,SIGNED_URL_SERVICE_ACCOUNT_EMAIL=${SA_EMAIL} \
  --add-volume mount-path=/data,type=cloud-storage,bucket=BUCKET_NAME,readonly=true
```

Omit `--service-account` when using the default Compute Engine service account
(Option B).

### Signed download links

Set `SIGNED_URL_BUCKET` to register the `download_link` tool. If
`SIGNED_URL_BUCKET` is not set, the tool is not registered.

`download_link` accepts a file path under `/data` and returns a structured
payload with a temporary V4 signed Cloud Storage URL:

```json
{
  "url": "https://storage.googleapis.com/BUCKET_NAME/path/file.pdf?...",
  "method": "GET",
  "expires_at": "2026-06-13T12:00:00Z",
  "expires_seconds": 900,
  "bucket": "BUCKET_NAME",
  "object": "path/file.pdf",
  "path": "path/file.pdf",
  "content_disposition": "attachment; filename=\"file.pdf\""
}
```

The bucket and objects remain private. The signed URL is a bearer URL, so anyone
with the URL can download that object until it expires.

For Cloud Run, set `SIGNED_URL_SERVICE_ACCOUNT_EMAIL` to the service account that
should sign URLs. Use the same `${SA_EMAIL}` from step 4 for both
`--service-account` and `SIGNED_URL_SERVICE_ACCOUNT_EMAIL` (or just
`SIGNED_URL_SERVICE_ACCOUNT_EMAIL` when using the default Compute Engine service
account and omitting `--service-account`).

When the runtime and signing accounts differ, grant
`roles/iam.serviceAccountTokenCreator` on the signing account to the Cloud Run
service account. The signing account also needs `roles/storage.objectViewer` on
the bucket.

### Notes on Cloud Storage mounts and search

`grep` and `pdfgrep` should work against a read-only Cloud Storage mount because
the tools only need normal directory and file reads. The image already includes
`ripgrep` and `pdfgrep`, and both tools operate on `/data`.

Important limitations:

- Cloud Run uses Cloud Storage FUSE for the mount, so searches over many or large
  files can be slower than searching a local disk.
- This server registers file resources at startup. Objects added to the bucket
  after an instance starts can still be found by direct filesystem searches, but
  they will not appear in the startup resource list until a new Cloud Run
  instance starts.
- Keep the mount read-only for this server. It does not need write access to the
  bucket.

References:

- [Cloud Run Cloud Storage volume mounts](https://cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)
- [gcloud run deploy reference](https://cloud.google.com/sdk/gcloud/reference/run/deploy)

### Publishing to Docker Hub

These are the steps used to publish `jamiewannenburg/resource-mcp:latest` after code changes (including the `NAMESPACE` support).

1. **Confirm Docker Desktop is running** (Linux). The daemon should respond:

   ```bash
   docker info
   ```

   If the socket is unreachable, start Docker Desktop and wait until `docker info` succeeds:

   ```bash
   docker desktop start
   ```

2. **Run tests** from the project virtualenv:

   ```bash
   ./venv/bin/pytest
   ```

3. **Build** the image from the repository root:

   ```bash
   docker build -t jamiewannenburg/resource-mcp:latest .
   ```

4. **Push** to Docker Hub (log in first with `docker login` if needed):

   ```bash
   docker push jamiewannenburg/resource-mcp:latest
   ```

5. **Push source** to GitHub when there are committed changes:

   ```bash
   git push origin main
   ```

### Mount a different directory

```yaml
# docker-compose.yml
volumes:
  - /path/to/your/files:/data:ro
```

## Configuration

### Application settings

| Variable                           | Default | Description                                      |
| ---------------------------------- | ------- | ------------------------------------------------ |
| `DATA_DIR`                         | `/data` | Directory whose files are exposed as resources   |
| `RECURSIVE`                        | `true`  | Include subdirectories when listing and indexing |
| `NAMESPACE`                        | *(none)* | Prefix tools and resource URIs to avoid name clashes when multiple MCP servers are combined |
| `SIGNED_URL_BUCKET`                | *(none)* | Cloud Storage bucket used by `download_link`; when unset, the tool is not registered |
| `SIGNED_URL_EXPIRES_SECONDS`       | `900`   | Default signed URL lifetime in seconds, maximum `604800` |
| `SIGNED_URL_SERVICE_ACCOUNT_EMAIL` | *(none)* | Optional service account email used for IAM-based URL signing on Cloud Run |

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
