import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.models import Query
from app.providers import Gateway
from app.service import InputError, Service
from app.store import Store

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


def create_app(service=None, store=None):
    app = FastAPI(title="Candidate Evidence Assistant")
    store = store or Store()

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default response can echo invalid input; omit it for privacy.
        return JSONResponse(status_code=422, content={"detail": "Invalid request fields."})

    @app.get("/health")
    def health():
        try:
            return {"status": "ready", "chunks": store.ready()}
        except Exception:
            return JSONResponse(status_code=503, content={"detail": "Index unavailable. Start DB and ingest."})

    @app.get("/candidates")
    def candidates():
        try:
            return {"candidate_ids": store.candidates()}
        except Exception:
            return JSONResponse(status_code=503, content={"detail": "Index unavailable."})

    @app.post("/ask")
    def ask(query: Query):
        try:
            active = service or Service(store, Gateway())
            return active.ask(query)
        except InputError as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"detail": "Service unavailable. Check DB, model access, API key and quota."},
            )

    return app


app = create_app()