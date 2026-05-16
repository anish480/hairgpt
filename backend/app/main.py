from fastapi import FastAPI

from app.config import settings

app = FastAPI(title="HairGPT Backend", version="0.0.1")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "project": settings.gcp_project_id,
        "location": settings.gcp_location,
        "shop": settings.shopify_shop,
    }
