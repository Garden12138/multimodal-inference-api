"""ASGI entrypoint. Configuration comes from the environment, never from this file."""

from inference.app_factory import create_app
from inference.config import load_settings

app = create_app(load_settings())
