from fastapi import APIRouter

from app.ai import service
from app.routers.dashboard import Database, DateRange
from app.schemas import Answer, AskRequest, Insights
from app.services.analytics import analytics_context

router = APIRouter(prefix="/api/ai", tags=["AI"])


@router.post("/ask", response_model=Answer)
def ask(body: AskRequest, db: Database, period: DateRange):
    service.require_ai()
    context = analytics_context(db, period)
    return Answer(answer=service.answer_question(body.question.strip(), context))


@router.get("/insights", response_model=Insights)
def insights(db: Database, period: DateRange):
    service.require_ai()
    return service.generate_insights(analytics_context(db, period))
