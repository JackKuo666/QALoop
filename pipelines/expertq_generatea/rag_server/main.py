"""Bio RAG Server - FastAPI service using Biopython (no ES required)"""
import os
import pkgutil
import importlib
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import sensor
from utils.bio_logger import bio_logger as logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup: dynamically import search services
    logger.info("Loading search services...")
    for _, module_name, _ in pkgutil.iter_modules(["search_service"]):
        importlib.import_module(f"search_service.{module_name}")
        logger.info(f"Loaded: search_service.{module_name}")
    yield
    # Shutdown


app = FastAPI(
    title="Bio RAG Server",
    description="Biomedical RAG service using PubMed (no Elasticsearch required)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(sensor.router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "bio-rag-server"}


if __name__ == "__main__":
    logger.info("Starting Bio RAG Server on port 9487...")
    uvicorn.run(app, host="0.0.0.0", port=9487)
