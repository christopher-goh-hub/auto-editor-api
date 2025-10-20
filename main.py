import os
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import boto3
import requests
from botocore.exceptions import ClientError
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, HttpUrl

app = FastAPI(title="Auto-Editor API", version="1.0.0")

# Wasabi Configuration
WASABI_ACCESS_KEY = os.getenv("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = os.getenv("WASABI_SECRET_KEY")
WASABI_BUCKET = os.getenv("WASABI_BUCKET")
WASABI_REGION = os.getenv("WASABI_REGION", "us-east-1")
WASABI_ENDPOINT = os.getenv("WASABI_ENDPOINT", f"https://s3.{WASABI_REGION}.wasabisys.com")
WASABI_ENABLED = all([WASABI_ACCESS_KEY, WASABI_SECRET_KEY, WASABI_BUCKET])

# Initialize S3 client if Wasabi is configured
s3_client = None
if WASABI_ENABLED:
    s3_client = boto3.client(
        's3',
        endpoint_url=WASABI_ENDPOINT,
        aws_access_key_id=WASABI_ACCESS_KEY,
        aws_secret_access_key=WASABI_SECRET_KEY,
        region_name=WASABI_REGION
    )

UPLOAD_DIR = Path("/tmp/uploads")
OUTPUT_DIR = Path("/tmp/outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

class ProcessingStatus(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
    output_file: Optional[str] = None
    wasabi_url: Optional[str] = None

class ProcessVideoFromUrl(BaseModel):
    url: str = Field(..., description="URL of the video file to process")
    margin: Optional[str] = Field(None, description="Margin for cuts (e.g., '0.2sec')")
    edit_mode: Optional[str] = Field(None, description="Edit mode: 'audio', 'motion', 'subtitle'")
    threshold: Optional[float] = Field(None, description="Threshold value for edit mode")

class JobStore:
    def __init__(self):
        self.jobs = {}

    def add_job(self, job_id: str, status: str, message: str = ""):
        self.jobs[job_id] = {"status": status, "message": message, "output_file": None, "wasabi_url": None}

    def update_job(self, job_id: str, status: str, message: str = "", output_file: str = None, wasabi_url: str = None):
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
            self.jobs[job_id]["message"] = message
            if output_file:
                self.jobs[job_id]["output_file"] = output_file
            if wasabi_url:
                self.jobs[job_id]["wasabi_url"] = wasabi_url

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

def download_video_from_url(url: str, output_path: Path) -> bool:
    """Download video from URL to local file"""
    try:
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        with output_path.open('wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading video from URL: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error downloading video: {e}")
        return False

def upload_to_wasabi(file_path: Path, job_id: str) -> Optional[str]:
    """Upload file to Wasabi and return a presigned URL (valid for 12 hours)"""
    if not WASABI_ENABLED or not s3_client:
        return None

    try:
        file_name = file_path.name
        s3_key = f"edited-videos/{job_id}/{file_name}"

        # Upload file (private, no public access)
        s3_client.upload_file(
            str(file_path),
            WASABI_BUCKET,
            s3_key
        )

        # Generate presigned URL valid for 12 hours (43200 seconds)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': WASABI_BUCKET,
                'Key': s3_key
            },
            ExpiresIn=43200  # 12 hours
        )

        return presigned_url

    except ClientError as e:
        print(f"Error uploading to Wasabi: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during Wasabi upload: {e}")
        return None

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
            # Upload to Wasabi if configured
            wasabi_url = None
            if WASABI_ENABLED:
                wasabi_url = upload_to_wasabi(output_path, job_id)
                if wasabi_url:
                    job_store.update_job(job_id, "completed", "Video processed and uploaded to Wasabi (presigned URL valid for 12 hours)",
                                       str(output_path), wasabi_url)
                    # Delete local output file after successful Wasabi upload to save disk space
                    try:
                        output_path.unlink()
                        print(f"Deleted local file after Wasabi upload: {output_path}")
                    except Exception as e:
                        print(f"Failed to delete local file: {e}")
                else:
                    job_store.update_job(job_id, "completed", "Video processed (Wasabi upload failed)",
                                       str(output_path))
            else:
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
            "POST /process-url": "Process a video from URL",
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

@app.post("/process-url", response_model=ProcessingStatus)
async def process_video_from_url_endpoint(
    background_tasks: BackgroundTasks,
    request: ProcessVideoFromUrl
):
    """
    Download a video from URL and process it with auto-editor.

    Parameters:
    - url: URL of the video file to process
    - margin: Add padding before/after cuts (e.g., '0.2sec')
    - edit_mode: Method for making cuts (default: 'audio')
    - threshold: Threshold value for the edit mode

    Returns job_id for tracking progress.
    """

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Determine file extension from URL
    url_path = Path(request.url)
    file_ext = url_path.suffix if url_path.suffix else ".mp4"

    input_path = UPLOAD_DIR / f"{job_id}_input{file_ext}"
    output_path = OUTPUT_DIR / f"{job_id}_output{file_ext}"

    # Create job
    job_store.add_job(job_id, "downloading", "Downloading video from URL")

    # Download video
    if not download_video_from_url(request.url, input_path):
        job_store.update_job(job_id, "failed", "Failed to download video from URL")
        raise HTTPException(status_code=400, detail="Failed to download video from URL")

    # Update job status and start processing
    job_store.update_job(job_id, "processing", "Video downloaded, processing started")
    background_tasks.add_task(process_video, job_id, input_path, output_path,
                             request.margin, request.edit_mode, request.threshold)

    return ProcessingStatus(
        job_id=job_id,
        status="processing",
        message="Video download started and will be processed"
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
        output_file=job["output_file"],
        wasabi_url=job.get("wasabi_url")
    )

@app.get("/download/{job_id}")
async def download_video(job_id: str, background_tasks: BackgroundTasks):
    """Download the processed video (if available locally)"""
    job = job_store.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job status: {job['status']}")

    output_file = Path(job["output_file"]) if job.get("output_file") else None

    # Check if file exists locally
    if not output_file or not output_file.exists():
        # If Wasabi URL is available, inform user
        if job.get("wasabi_url"):
            raise HTTPException(
                status_code=410,
                detail="Local file has been removed after Wasabi upload. Please use the wasabi_url from the status endpoint."
            )
        else:
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
    return {
        "status": "healthy",
        "wasabi_enabled": WASABI_ENABLED,
        "wasabi_bucket": WASABI_BUCKET if WASABI_ENABLED else None
    }
