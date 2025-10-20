import os
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Auto-Editor API", version="1.0.0")

UPLOAD_DIR = Path("/tmp/uploads")
OUTPUT_DIR = Path("/tmp/outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

class ProcessingStatus(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
    output_file: Optional[str] = None

class JobStore:
    def __init__(self):
        self.jobs = {}

    def add_job(self, job_id: str, status: str, message: str = ""):
        self.jobs[job_id] = {"status": status, "message": message, "output_file": None}

    def update_job(self, job_id: str, status: str, message: str = "", output_file: str = None):
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
            self.jobs[job_id]["message"] = message
            if output_file:
                self.jobs[job_id]["output_file"] = output_file

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

job_store = JobStore()

def cleanup_file(path: Path):
    """Background task to cleanup files after download"""
    try:
        if path.exists():
            path.unlink()
    except Exception as e:
        print(f"Error cleaning up {path}: {e}")

def process_video(job_id: str, input_path: Path, output_path: Path, margin: Optional[str],
                  edit_mode: Optional[str], threshold: Optional[float]):
    """Process video using auto-editor"""
    try:
        cmd = ["auto-editor", str(input_path), "-o", str(output_path)]

        if margin:
            cmd.extend(["--margin", margin])

        if edit_mode:
            if threshold:
                cmd.extend(["--edit", f"{edit_mode}:threshold={threshold}"])
            else:
                cmd.extend(["--edit", edit_mode])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

        if result.returncode == 0:
            job_store.update_job(job_id, "completed", "Video processed successfully", str(output_path))
        else:
            job_store.update_job(job_id, "failed", f"Auto-editor error: {result.stderr}")

    except subprocess.TimeoutExpired:
        job_store.update_job(job_id, "failed", "Processing timeout (>1 hour)")
    except Exception as e:
        job_store.update_job(job_id, "failed", f"Processing error: {str(e)}")
    finally:
        # Cleanup input file
        try:
            input_path.unlink()
        except:
            pass

@app.get("/")
async def root():
    return {
        "message": "Auto-Editor API",
        "docs": "/docs",
        "endpoints": {
            "POST /process": "Upload and process a video",
            "GET /status/{job_id}": "Check processing status",
            "GET /download/{job_id}": "Download processed video"
        }
    }

@app.post("/process", response_model=ProcessingStatus)
async def process_video_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    margin: Optional[str] = Query(None, description="Margin for cuts (e.g., '0.2sec' or '0.3s,1.5s')"),
    edit_mode: Optional[str] = Query(None, description="Edit mode: 'audio', 'motion', 'subtitle', etc."),
    threshold: Optional[float] = Query(None, description="Threshold value for edit mode")
):
    """
    Upload a video file and process it with auto-editor.

    Parameters:
    - file: Video file to process
    - margin: Add padding before/after cuts (e.g., '0.2sec')
    - edit_mode: Method for making cuts (default: 'audio')
    - threshold: Threshold value for the edit mode

    Returns job_id for tracking progress.
    """

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Save uploaded file
    file_ext = Path(file.filename).suffix
    input_path = UPLOAD_DIR / f"{job_id}_input{file_ext}"
    output_path = OUTPUT_DIR / f"{job_id}_output{file_ext}"

    try:
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")

    # Create job and start processing
    job_store.add_job(job_id, "processing", "Video is being processed")
    background_tasks.add_task(process_video, job_id, input_path, output_path, margin, edit_mode, threshold)

    return ProcessingStatus(
        job_id=job_id,
        status="processing",
        message="Video processing started"
    )

@app.get("/status/{job_id}", response_model=ProcessingStatus)
async def get_status(job_id: str):
    """Check the status of a processing job"""
    job = job_store.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return ProcessingStatus(
        job_id=job_id,
        status=job["status"],
        message=job["message"],
        output_file=job["output_file"]
    )

@app.get("/download/{job_id}")
async def download_video(job_id: str, background_tasks: BackgroundTasks):
    """Download the processed video"""
    job = job_store.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job status: {job['status']}")

    output_file = Path(job["output_file"])

    if not output_file.exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    # Schedule cleanup after download
    background_tasks.add_task(cleanup_file, output_file)

    return FileResponse(
        path=output_file,
        filename=f"edited_{output_file.name}",
        media_type="video/mp4"
    )

@app.delete("/cleanup/{job_id}")
async def cleanup_job(job_id: str):
    """Manually cleanup job files"""
    job = job_store.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Remove output file if exists
    if job["output_file"]:
        try:
            Path(job["output_file"]).unlink()
        except:
            pass

    # Remove from job store
    del job_store.jobs[job_id]

    return {"message": "Job cleaned up successfully"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
