# Sea-to-Sky Traffic Prediction

Day-ahead prediction of when and where northbound traffic builds on Highway 99
(Vancouver → Whistler). Non-commercial UBC student project. See `CLAUDE.md` for the
problem definition, data sources and deployment decisions.

## Setup

```bash
uv sync                      # dev + parse groups (default)
uv sync --group logger       # add logger deps (boto3, sr3)
uv run pytest
uv run ruff check
```

## Webcam logger

```bash
cp .env.example .env         # fill in; never commit .env
uv run --group logger --env-file .env python -m whistler_traffic.logger.webcams
```

On the server the logger runs as a systemd unit (see `deploy/`). `requirements.txt` holds
the logger's pinned dependencies, exported from `uv.lock`:

```bash
uv export --frozen --no-default-groups --group logger -o requirements.txt
```

## Attribution

- Contains information licensed under the Open Government Licence – British Columbia.
- Data Source: Environment and Climate Change Canada.
