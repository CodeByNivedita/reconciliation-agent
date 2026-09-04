

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.services import reconciliation_service as svc
from backend.evaluation.evaluator import evaluate

app = FastAPI(title="Reconciliation Agent API")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/queue/summary")
def queue_summary():
    return svc.get_queue_summary()


@app.get("/api/cases")
def list_cases(action: str | None = None, category: str | None = None):
    return svc.list_cases(action=action, category=category)


@app.get("/api/cases/{order_id}")
def case_detail(order_id: str):
    detail = svc.get_case_detail(order_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No such order: {order_id}")
    return detail


@app.get("/api/benchmark")
def benchmark(split: str | None = None):
    return evaluate(split)


@app.get("/health")
def health():
    return {"status": "ok"}
