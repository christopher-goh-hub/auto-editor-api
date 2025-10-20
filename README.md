# Auto-Editor API

A RESTful API wrapper for [auto-editor](https://github.com/WyattBlue/auto-editor) that automatically edits videos by cutting silent parts. Built with FastAPI and Docker.

## Features

- Automatically remove silent sections from videos
- Adjustable margin/padding around cuts
- Multiple edit modes (audio, motion, subtitle)
- Asynchronous processing with job tracking
- **Automatic upload to Wasabi cloud storage**
- Docker deployment with Debian Slim (lightweight)
- RESTful API with OpenAPI documentation

## Wasabi Configuration (Optional)

The API can automatically upload processed videos to Wasabi cloud storage with presigned URLs for secure access.

### Features:
- **Private storage**: Files are kept private (no public-read permissions needed)
- **Presigned URLs**: Secure, time-limited URLs valid for 12 hours
- **Auto-cleanup**: Local files are automatically deleted after successful upload to save disk space

### Setup:

1. Create a `.env` file from the example:
```bash
cp .env.example .env
```

2. Edit `.env` with your Wasabi credentials:
```bash
WASABI_ACCESS_KEY=your_access_key_here
WASABI_SECRET_KEY=your_secret_key_here
WASABI_BUCKET=your_bucket_name
WASABI_REGION=us-east-1  # Optional, defaults to us-east-1
```

3. **No public access needed**: Your bucket can remain private. The API generates presigned URLs that expire after 12 hours.

4. Start the service:
```bash
docker-compose up -d
```

When Wasabi is configured, processed videos will automatically be uploaded and a presigned `wasabi_url` (valid for 12 hours) will be included in the status response.

### Available Wasabi Regions

- `us-east-1` (Northern Virginia)
- `us-east-2` (Northern Virginia)
- `us-west-1` (Oregon)
- `eu-central-1` (Amsterdam)
- `ap-northeast-1` (Tokyo)
- `ap-northeast-2` (Osaka)

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Build and start the service
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop the service
docker-compose down
```

The API will be available at `http://localhost:8000`

### Using Docker

```bash
# Build the image
docker build -t auto-editor-api .

# Run the container
docker run -d -p 8000:8000 --name auto-editor-api auto-editor-api

# Check logs
docker logs -f auto-editor-api
```

## API Endpoints

### 1. Process Video

Upload and process a video file.

**Endpoint:** `POST /process`

**Parameters:**
- `file` (required): Video file to process
- `margin` (optional): Add padding before/after cuts (e.g., `0.2sec` or `0.3s,1.5s`)
- `edit_mode` (optional): Method for making cuts (`audio`, `motion`, `subtitle`)
- `threshold` (optional): Threshold value for the edit mode

**Example:**

```bash
curl -X POST "http://localhost:8000/process?margin=0.2sec" \
  -F "file=@video.mp4"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Video processing started"
}
```

### 2. Process Video from URL

Process a video from a URL (no file upload needed).

**Endpoint:** `POST /process-url`

**Request Body (JSON):**
- `url` (required): URL of the video file to process
- `margin` (optional): Add padding before/after cuts (e.g., `0.2sec`)
- `edit_mode` (optional): Method for making cuts (`audio`, `motion`, `subtitle`)
- `threshold` (optional): Threshold value for the edit mode

**Example:**

```bash
curl -X POST "http://localhost:8000/process-url" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://tempfile.aiquickdraw.com/v/9131a9aed35b5a32026ac4ae303dcd47_1760889483.mp4",
    "threshold": 0.05
  }'
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Video download started and will be processed"
}
```

### 3. Check Status

Check the processing status of a job.

**Endpoint:** `GET /status/{job_id}`

**Example:**

```bash
curl "http://localhost:8000/status/550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "message": "Video processed and uploaded to Wasabi (presigned URL valid for 12 hours)",
  "output_file": "/tmp/outputs/550e8400-e29b-41d4-a716-446655440000_output.mp4",
  "wasabi_url": "https://s3.us-east-1.wasabisys.com/your-bucket/edited-videos/550e8400-e29b-41d4-a716-446655440000/550e8400-e29b-41d4-a716-446655440000_output.mp4?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=..."
}
```

**Important Notes:**
- `wasabi_url` is a **presigned URL valid for 12 hours** from generation time
- After successful Wasabi upload, the **local file is automatically deleted** to save disk space
- Use the presigned URL to download the video (not the `/download` endpoint when using Wasabi)

### 4. Download Processed Video

Download the processed video file from the API server (only works if file is still stored locally).

**Endpoint:** `GET /download/{job_id}`

**Example:**

```bash
curl -O -J "http://localhost:8000/download/550e8400-e29b-41d4-a716-446655440000"
```

**Note:** When Wasabi is enabled, local files are automatically deleted after upload. In this case, use the `wasabi_url` from the status response instead.

### 5. Cleanup Job

Manually cleanup job files and remove from tracking.

**Endpoint:** `DELETE /cleanup/{job_id}`

**Example:**

```bash
curl -X DELETE "http://localhost:8000/cleanup/550e8400-e29b-41d4-a716-446655440000"
```

### 6. Health Check

Check if the API is running.

**Endpoint:** `GET /health`

**Example:**

```bash
curl "http://localhost:8000/health"
```

## Complete Workflow Examples

### File Upload Workflow

```bash
# 1. Upload and process a video
JOB_ID=$(curl -s -X POST "http://localhost:8000/process?margin=0.2sec" \
  -F "file=@video.mp4" | jq -r '.job_id')

echo "Job ID: $JOB_ID"

# 2. Check status (repeat until completed)
while true; do
  STATUS=$(curl -s "http://localhost:8000/status/$JOB_ID" | jq -r '.status')
  echo "Status: $STATUS"

  if [ "$STATUS" = "completed" ]; then
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "Processing failed"
    exit 1
  fi

  sleep 5
done

# 3. Get the Wasabi URL (if configured) or download from API
WASABI_URL=$(curl -s "http://localhost:8000/status/$JOB_ID" | jq -r '.wasabi_url')
if [ "$WASABI_URL" != "null" ]; then
  echo "Video available at: $WASABI_URL"
  # Download from Wasabi if needed
  curl -o edited_video.mp4 "$WASABI_URL"
else
  # Download from API server
  curl -O -J "http://localhost:8000/download/$JOB_ID"
fi

# 4. Cleanup job metadata (optional)
curl -X DELETE "http://localhost:8000/cleanup/$JOB_ID"
```

### URL Processing Workflow

```bash
# 1. Process video from URL
JOB_ID=$(curl -s -X POST "http://localhost:8000/process-url" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://tempfile.aiquickdraw.com/v/example.mp4",
    "threshold": 0.05
  }' | jq -r '.job_id')

echo "Job ID: $JOB_ID"

# 2. Check status (repeat until completed)
while true; do
  RESPONSE=$(curl -s "http://localhost:8000/status/$JOB_ID")
  STATUS=$(echo $RESPONSE | jq -r '.status')
  echo "Status: $STATUS"

  if [ "$STATUS" = "completed" ]; then
    # Get Wasabi URL if available
    WASABI_URL=$(echo $RESPONSE | jq -r '.wasabi_url')
    if [ "$WASABI_URL" != "null" ]; then
      echo "Video available at: $WASABI_URL"
    fi
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "Processing failed"
    exit 1
  fi

  sleep 5
done

# 3. Download from Wasabi (if available)
if [ "$WASABI_URL" != "null" ]; then
  curl -o edited_video.mp4 "$WASABI_URL"
fi
```

## Python Client Examples

### File Upload

```python
import requests
import time

# Upload video
with open('video.mp4', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/process',
        params={'margin': '0.2sec'},
        files={'file': f}
    )

job_id = response.json()['job_id']
print(f"Job ID: {job_id}")

# Poll for completion
while True:
    status_response = requests.get(f'http://localhost:8000/status/{job_id}')
    status_data = status_response.json()

    print(f"Status: {status_data['status']}")

    if status_data['status'] == 'completed':
        break
    elif status_data['status'] == 'failed':
        print(f"Error: {status_data['message']}")
        exit(1)

    time.sleep(5)

# Check if Wasabi URL is available
if status_data.get('wasabi_url'):
    print(f"Presigned URL (valid 12 hours): {status_data['wasabi_url']}")
    # Download from Wasabi
    download_response = requests.get(status_data['wasabi_url'])
    with open('edited_video.mp4', 'wb') as f:
        f.write(download_response.content)
    print("Video downloaded from Wasabi successfully!")
else:
    # Download processed video from API server
    download_response = requests.get(f'http://localhost:8000/download/{job_id}')
    with open('edited_video.mp4', 'wb') as f:
        f.write(download_response.content)
    print("Video downloaded from API server successfully!")
```

### URL Processing

```python
import requests
import time

# Process video from URL
response = requests.post(
    'http://localhost:8000/process-url',
    json={
        'url': 'https://tempfile.aiquickdraw.com/v/example.mp4',
        'threshold': 0.05
    }
)

job_id = response.json()['job_id']
print(f"Job ID: {job_id}")

# Poll for completion
while True:
    status_response = requests.get(f'http://localhost:8000/status/{job_id}')
    status_data = status_response.json()

    print(f"Status: {status_data['status']}")

    if status_data['status'] == 'completed':
        break
    elif status_data['status'] == 'failed':
        print(f"Error: {status_data['message']}")
        exit(1)

    time.sleep(5)

# Check if Wasabi URL is available
if status_data.get('wasabi_url'):
    print(f"Presigned URL (valid 12 hours): {status_data['wasabi_url']}")
    # Download from Wasabi
    download_response = requests.get(status_data['wasabi_url'])
    with open('edited_video.mp4', 'wb') as f:
        f.write(download_response.content)
    print("Video downloaded from Wasabi successfully!")
else:
    # Download processed video from API server
    download_response = requests.get(f'http://localhost:8000/download/{job_id}')
    with open('edited_video.mp4', 'wb') as f:
        f.write(download_response.content)
    print("Video downloaded from API server successfully!")
```

## Configuration Options

### Margin

Add padding before/after cuts to make transitions smoother:

```bash
# Single value (same for before and after)
?margin=0.2sec

# Different values for before and after
?margin=0.3s,1.5s
```

### Edit Modes

Different methods for detecting sections to cut:

- `audio` (default): Cut based on audio loudness
- `motion`: Cut based on video motion
- `subtitle`: Cut based on subtitle presence

```bash
# Use motion detection
?edit_mode=motion

# Use motion with custom threshold
?edit_mode=motion&threshold=0.02
```

## API Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Architecture

- **FastAPI**: Modern Python web framework
- **Auto-Editor**: CLI tool for video editing
- **Debian Slim**: Lightweight Docker base image with glibc
- **FFmpeg**: Video processing backend
- **Boto3**: AWS SDK for S3-compatible storage (Wasabi)
- **Wasabi**: Optional cloud storage for processed videos

## Project Structure

```
auto-editor-api2/
├── main.py              # FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Multi-stage Debian build
├── docker-compose.yml  # Docker Compose config
├── .env.example        # Wasabi configuration template
├── .dockerignore       # Docker build exclusions
├── .gitignore          # Git exclusions
└── README.md           # This file
```

## Performance Notes

- Processing time depends on video length and complexity
- Jobs timeout after 1 hour
- Temporary files are automatically cleaned up after download
- Use the `/cleanup` endpoint for manual cleanup

## Troubleshooting

### Container won't start

Check logs:
```bash
docker-compose logs -f
```

### Out of disk space

Clean up Docker resources:
```bash
docker system prune -a
```

### Processing takes too long

Consider:
- Reducing video resolution
- Shortening video length
- Adjusting timeout in `main.py:76`

## License

This API wrapper is provided as-is. Auto-editor is licensed under the Public Domain.

## Credits

Built on top of [auto-editor](https://github.com/WyattBlue/auto-editor) by WyattBlue.
