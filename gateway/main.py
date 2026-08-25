import uvicorn

from gateway.api import create_app
from gateway.config import Settings
from gateway.logging_config import configure_logging

settings = Settings.from_env()
configure_logging(settings.log_dir)
app = create_app(settings)

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
