from fastapi import APIRouter, Depends

from app.services.prediction_service import PredictionService

router = APIRouter(prefix="/sign", tags=["sign"])


def get_prediction_service() -> PredictionService:
    return PredictionService.from_settings()


@router.get("/status")
def get_status(service: PredictionService = Depends(get_prediction_service)):
    return service.status()


@router.get("/vocabulary")
def get_vocabulary(sign_type: str | None = None, service: PredictionService = Depends(get_prediction_service)):
    iterator = service.recognizer.vocabulary(sign_type=sign_type)
    return {"items": list(iterator)}