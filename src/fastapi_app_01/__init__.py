def main() -> None:
    import uvicorn
    uvicorn.run("my_fastapi_app.main:app", host="127.0.0.1", port=8000, reload=True)
