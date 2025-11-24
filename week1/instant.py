from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def instant():
    return "Nikhil: Live from production!"