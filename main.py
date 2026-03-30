"""Application entry point."""
import uvicorn
from config.settings import settings

from api.main import app  # noqa: F401 — re-export so `uvicorn main:app` works

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
