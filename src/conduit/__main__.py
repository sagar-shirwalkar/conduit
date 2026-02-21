import sys

import uvicorn

from conduit.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "conduit.app:create_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        workers=settings.server.workers,
        log_level=settings.logging.level.lower(),
    )


if __name__ == "__main__":
    sys.exit(main())  # type: ignore[func-returns-value]