from fastapi import APIRouter, HTTPException

from src.api.schemas import ClassifyRequest, ClassifyResponse

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest) -> ClassifyResponse:
    raise HTTPException(status_code=501, detail="RAG pipeline not yet implemented")
