from pathlib import Path
import shutil
import tempfile
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .pdf2tts import pdf_to_mp3_with_ttsfm


app = FastAPI(title="PDF to TTS Service", version="0.1.0")

@app.post("/convert")
async def convert_pdf(
    pdf: UploadFile = File(..., description="PDF file to convert"),
    voice: str = Form("alloy"),
    speed: float = Form(1.0),
    max_length: int = Form(1000),
    start_page: Optional[int] = Form(None),
    end_page: Optional[int] = Form(None),
    background_tasks: BackgroundTasks = None,
):
    if pdf.content_type not in ("application/pdf", "application/octet-stream", None):
        raise HTTPException(status_code=400, detail="Unsupported file type, please upload a PDF.")

    if background_tasks is None:
        background_tasks = BackgroundTasks()

    temp_dir = Path(tempfile.mkdtemp(prefix="pdf2tts_"))
    pdf_path = temp_dir / (Path(pdf.filename or "input.pdf").name)
    mp3_path = temp_dir / f"{pdf_path.stem}.mp3"

    try:
        pdf_bytes = await pdf.read()
        pdf_path.write_bytes(pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Failed to read uploaded PDF.") from exc

    try:
        await run_in_threadpool(
            pdf_to_mp3_with_ttsfm,
            str(pdf_path),
            str(mp3_path),
            voice,
            speed,
            max_length,
            start_page,
            end_page,
        )
    except ValueError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="Failed to generate audio.") from exc

    background_tasks.add_task(shutil.rmtree, temp_dir, ignore_errors=True)
    return FileResponse(
        path=str(mp3_path),
        media_type="audio/mpeg",
        filename=f"{pdf_path.stem}.mp3",
        background=background_tasks,
    )
