import asyncio
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from image_find import get_accessible_image_url as get_image_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Image Find API")


class SearchRequest(BaseModel):
    q: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/image")
async def find_image(body: SearchRequest):
    query = (body.q or "").strip()
    if not query:
        return JSONResponse({"error": "Missing 'q'"}, status_code=400)

    try:
        img_url = await asyncio.to_thread(get_image_url, query)
    except Exception as exc:
        logger.exception("Image search failed for query=%r", query)
        return JSONResponse({"error": "Image search failed"}, status_code=500)

    if img_url:
        return JSONResponse({"image_url": img_url})

    return JSONResponse({"error": "No image found"}, status_code=404)


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 7016))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
