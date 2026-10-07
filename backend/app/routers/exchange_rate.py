from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas import ExchangeRate
from app.services.exchange_rate import ExchangeRateService, get_exchange_rate_service

router = APIRouter(prefix="/api", tags=["Exchange rate"])


@router.get("/exchange-rate", response_model=ExchangeRate)
def get_exchange_rate(service: Annotated[ExchangeRateService, Depends(get_exchange_rate_service)]):
    return service.get_rate()
