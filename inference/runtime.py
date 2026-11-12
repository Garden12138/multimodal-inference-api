"""Load .env without overriding the process environment, then serve the API."""

from __future__ import annotations

from pathlib import Path

import uvicorn

from inference.config import ROOT, load_env_file, load_settings


def main() -> None:
    load_env_file(ROOT / ".env")
    settings = load_settings()
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
