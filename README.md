# clavis-samidare

SAMIDARE board plugin for `clavis`.

Install locally while developing:

```bash
uv pip install -e path/to/clavis-samidare
```

The package registers a `clavis.boards` entry point with board type `samidare`.

## Docker image

Build the core Clavis image first, or use a published core image as the base.
From this repository, build the plugin-equipped daemon image with:

```bash
docker build \
  --build-arg CLAVIS_BASE_IMAGE=ghcr.io/OWNER/clavis:0.1.0 \
  -t ghcr.io/OWNER/clavis-samidare:0.1.0 \
  .
```

Publish it with:

```bash
docker login ghcr.io
docker push ghcr.io/OWNER/clavis-samidare:0.1.0
```

Select this image when running the Compose file from the `clavis` repository.
The same running container provides the daemon and on-demand CLI commands:

```bash
export CLAVIS_DAEMON_IMAGE=ghcr.io/OWNER/clavis-samidare:0.1.0
docker compose up --no-build -d daemon
docker exec clavis clavis boards types
```
