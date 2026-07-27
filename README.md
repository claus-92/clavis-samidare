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

To build a local plugin-equipped image after building `clavis:local`:

```bash
docker build --build-arg CLAVIS_BASE_IMAGE=clavis:local -t clavis-samidare:local .
```

## License

Clavis SAMIDARE is licensed under the [Apache License 2.0](LICENSE).

## Citing the plugin

If this plugin contributes to published work, cite it using the metadata in
[`CITATION.cff`](CITATION.cff). Cite Clavis core separately when appropriate.
