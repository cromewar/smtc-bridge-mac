#!/bin/sh
cd "$(dirname "$0")" && exec uv run python -m smtc_bridge
