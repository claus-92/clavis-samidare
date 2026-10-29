# Clavis SAMIDARE plugin

This package adds SAMIDARE acquisition-board support to
[Clavis](https://github.com/claus-92/clavis). It communicates with the board
using the core fakernet register client over UDP.

## Development setup

From the Clavis repository:

```bash
uv sync --extra test
uv pip install -e ../clavis-samidare
uv run pytest ../clavis-samidare/tests
uv run clavis boards types
```

See the [configuration and operation guide](docs/configuration.md) before using
real hardware. Register addresses and supported firmware assumptions are
documented in [hardware notes](docs/hardware.md).

## Docker Compose

Keep the two repositories next to each other on the Docker host:

```text
CLAVIS/
├── clavis/
└── clavis-samidare/
```

From `clavis-samidare`, build and start the plugin-equipped daemon and its
Caddy HTTP proxy:

```bash
docker compose up -d --build
```

This requires Docker Compose 2.17 or newer and a BuildKit-enabled builder.
Compose builds both local packages using `Dockerfile.compose`; no prebuilt
`clavis:local` image is needed. The daemon and proxy settings are inherited
from `../clavis/compose.yaml`.

Check that the daemon is healthy and exposes SAMIDARE support:

```bash
docker compose ps
docker compose exec daemon clavis boards types
curl http://localhost:8000/api/status
```

The default image is `clavis-samidare:local`, and the default HTTP port is
`8000`. Set `CLAVIS_DAEMON_IMAGE`, `CLAVIS_PORT`, or `CLAVIS_RUNTIME_GID` in
the environment or a `.env` file to override the inherited settings.

## Building an image from an existing core image

To build a local plugin-equipped image after building `clavis:local`, run
from `clavis-samidare`:

```bash
docker build --build-arg CLAVIS_BASE_IMAGE=clavis:local -t clavis-samidare:local .
```

## License

Clavis SAMIDARE is licensed under the [Apache License 2.0](LICENSE).

## Citing the plugin

If this plugin contributes to published work, cite it using the metadata in
[`CITATION.cff`](CITATION.cff). Cite Clavis core separately when appropriate.
