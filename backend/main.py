"""FastAPI server: upload a PDF, review the parsed cabinets, generate cut lists."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import drawing, engine, parser

MAX_UPLOAD = 30 * 1024 * 1024
STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Cabinet cut list generator")


class Cabinet(BaseModel):
    ref: str = ""
    type: str = "base"
    w: float
    h: float
    d: float | None = None
    qty: int = 1
    doors: int = 0
    drawers: int = 0
    shelves: int = 0
    t: float | None = None
    base_h: float | None = None
    base_d: float | None = None
    header_h: float | None = None
    group: str = ""


class GenerateRequest(BaseModel):
    cabinets: list[Cabinet] = Field(..., min_length=1)
    settings: dict = Field(default_factory=dict)


@app.get("/api/defaults")
def defaults():
    return {"settings": engine.DEFAULTS, "depths": engine.DEFAULT_DEPTH}


@app.post("/api/parse")
async def parse(file: UploadFile = File(...), order: str = Form("WHD")):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "PDF is larger than 30 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "That file is not a PDF")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        return parser.parse_pdf(path, order)
    except Exception as e:  # OCR/rasterising failures are reported, not crashed
        raise HTTPException(422, f"Could not read the PDF: {e}")
    finally:
        os.unlink(path)


@app.post("/api/parse-drawing")
async def parse_drawing(file: UploadFile = File(...)):
    """Read bays from vector elevation drawings (any sheet size, A1 included)."""
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "PDF is larger than 30 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "That file is not a PDF")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        return drawing.read_drawing(path)
    except Exception as e:
        raise HTTPException(422, f"Could not read the drawing: {e}")
    finally:
        os.unlink(path)


@app.post("/api/generate")
def generate(req: GenerateRequest):
    return engine.generate([c.model_dump() for c in req.cabinets], req.settings)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
