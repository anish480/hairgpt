import logging
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from contextlib import asynccontextmanager

from app.config import settings
from app.db import close as close_db
from app.llm import classify_hair_photo, format_classification_summary
from app.orchestrator import chat


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await close_db()


app = FastAPI(title="HairGPT Backend", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    history: list[dict] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str
    session_id: str
    history: list[dict]
    suggested_options: list[str] = Field(default_factory=list)


class PhotoAnalysisResponse(BaseModel):
    classification: dict
    summary: str


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "project": settings.gcp_project_id,
        "location": settings.gcp_location,
        "shop": settings.shopify_shop,
    }


@app.post("/chat")
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    session_id = req.session_id or str(uuid.uuid4())
    response_text, updated_history, options = await chat(req.message, req.history)
    return ChatResponse(
        response=response_text,
        session_id=session_id,
        history=updated_history,
        suggested_options=options,
    )


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


logger = logging.getLogger(__name__)


@app.post("/photo/analyze")
async def analyze_photo(file: UploadFile = File(...)) -> PhotoAnalysisResponse:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Unsupported image type: {file.content_type}. Use JPEG, PNG, WebP, or HEIC.")
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image too large. Max 10 MB.")
    try:
        classification = await classify_hair_photo(image_bytes, file.content_type)
    except Exception:
        logger.exception("classify_hair_photo failed")
        raise
    summary = format_classification_summary(classification)
    return PhotoAnalysisResponse(classification=classification, summary=summary)
