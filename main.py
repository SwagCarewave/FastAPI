from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "CareWave FastAPI Server"}

# uvicorn main:app --reload