# Cabinet Workshop

A free, standalone cabinet cut-list companion for workshop planning. It generates panel sizes and face areas, edge-banding totals, hardware quantities and board nesting estimates. The browser app includes an editable interactive 3D cabinet view.

**Website:** [https://github.com/](https://github.com/)

## Run the app

Requires Python 3.10 or newer. Install the web-app dependencies and start the local server:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --port 8000
```

Open http://localhost:8000. Scanned PDF OCR is optional. Install `requirements-pdf-ocr.txt`, Tesseract and Poppler for OCR. Text-layer schedule parsing and cabinet generation work without Pillow.

## Built-in MCP server

The `Cabinet Workshop Cutlist` MCP stdio bridge uses Python's standard library; it does not require the external MCP SDK or Pillow:

```powershell
python launch_mcp.py
```

It provides `archicad_instances`, `archicad_cabinets`, `cutlist_generate`, and `cutlist_export` tools. For MCP-host configuration, use the path to your Python executable and the absolute path to `launch_mcp.py` as its argument.

## Archicad 28

This is an external companion, not a native Archicad add-on. The optional read-only bridge calls the local Archicad JSON API and reads selected object bounding boxes. It does not write back to Archicad. Type classification and door/drawer/shelf counts may be inferred and must be checked before manufacturing. The live Archicad 28 connection has not yet been verified.

## Checks

```powershell
python tests/test_engine.py
python tests/test_builtin_mcp.py
python tests/test_builtin_archicad.py
python tests/test_area.py
```

The checked Archicad adapter test uses mocked responses. PDF drawing-specific tests need the source drawing and OCR dependencies.

## License

MIT. See [LICENSE](LICENSE).
