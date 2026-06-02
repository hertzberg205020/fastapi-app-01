from urllib.parse import urlparse

from fastapi import FastAPI

from fastapi_app_01.config import settings

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/health")
def health():
    # Proves the config was loaded at startup. We never return the password —
    # just confirm where the app is pointed, parsed from DATABASE_URL.
    db = urlparse(settings.database_url)
    return {
        "database": {"host": db.hostname, "port": db.port, "name": db.path.lstrip("/")},
        "redis_configured": bool(settings.redis_url),
    }


if __name__ == "__main__":
    from fastapi_app_01 import main

    main()
