import uvicorn

from gateway.api import create_app
from gateway.config import Settings

settings = Settings.from_env()
app = create_app(settings)

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
