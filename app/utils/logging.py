"""Logging configuration for local development and API startup."""

import logging


def configure_logging(debug: bool = False) -> None:
    """Configure root logging with a concise default format."""

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

