import os


def main() -> None:
    import uvicorn

    # Reload is great for normal dev (auto-restart on code change) but spawns a
    # child process the debugger can't attach to. Set UVICORN_RELOAD=false (the
    # "debug" run config does this) to run single-process so breakpoints work.
    reload = os.getenv("UVICORN_RELOAD", "true").lower() == "true"
    uvicorn.run("fastapi_app_01.main:app", host="127.0.0.1", port=8000, reload=reload)
