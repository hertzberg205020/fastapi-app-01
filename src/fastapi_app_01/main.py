from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}


if __name__ == "__main__":
    from fastapi_app_01 import main

    main()
