def main() -> None:
    import uvicorn
    uvicorn.run("fastapi_app_01.main:app", host="127.0.0.1", port=8000, reload=True)
