import os
import json
import logging
import asyncio
import requests
from fastapi import FastAPI, Request, BackgroundTasks
from dotenv import load_dotenv
from fastapi import Response
import sys
# Ensure project root is on sys.path so local packages import correctly when running main.py
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from handlers.bitbucket_handler import process_bitbucket_event
from handlers.teams_handler import process_teams_event
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI()




@app.middleware("http")
async def add_ngrok_skip_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response
@app.post("/webhook/teams")
async def teams_webhook(request: Request, background_tasks: BackgroundTasks):
    body_bytes = await request.body()
    logger.info(f"🔍 Dữ liệu thô nhận được: {body_bytes.decode()}")
    try:
        data = await request.json()
        result = await process_teams_event(data, background_tasks)
        return result
    except Exception as e:
        logger.error(f"❌ Lỗi xử lý Webhook: {e}")
        return {"status": "error", "jira_message": f"❌ Lỗi: {str(e)}"}


@app.post("/webhook/bitbucket")
async def bitbucket_webhook(request: Request):
    body_bytes = await request.body()
    logger.info(f"🔍 Bitbucket raw: {body_bytes.decode()}")
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"❌ JSON parse error from Bitbucket: {e}")
        return {"status": "error", "message": "Invalid JSON"}

    try:
        result = process_bitbucket_event(data)
        status = "success" if result.get("success") else "error"
        return {"status": status, "result": result}
    except Exception as e:
        logger.error(f"❌ Lỗi xử lý Bitbucket webhook: {e}")
        return {"status": "error", "message": str(e)}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    