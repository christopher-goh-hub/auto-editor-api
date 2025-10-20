# Auto-Editor API

A RESTful API wrapper for [auto-editor](https://github.com/WyattBlue/auto-editor) that automatically edits videos by cutting silent parts. Built with FastAPI and Docker.

## Features

- Automatically remove silent sections from videos
- Adjustable margin/padding around cuts
- Multiple edit modes (audio, motion, subtitle)
- Asynchronous processing with job tracking
- Docker deployment with Alpine Linux (lightweight)
- RESTful API with OpenAPI documentation

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

### 2. Check Status

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
  "message": "Video processed successfully",
  "output_file": "/tmp/outputs/550e8400-e29b-41d4-a716-446655440000_output.mp4"
}
```

### 3. Download Processed Video

Download the processed video file.

**Endpoint:** `GET /download/{job_id}`

**Example:**

```bash
curl -O -J "http://localhost:8000/download/550e8400-e29b-41d4-a716-446655440000"
```

### 4. Cleanup Job

Manually cleanup job files and remove from tracking.

**Endpoint:** `DELETE /cleanup/{job_id}`

**Example:**

```bash
curl -X DELETE "http://localhost:8000/cleanup/550e8400-e29b-41d4-a716-446655440000"
```

### 5. Health Check

Check if the API is running.

**Endpoint:** `GET /health`

**Example:**

```bash
curl "http://localhost:8000/health"
```

## Complete Workflow Example

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

# 3. Download the processed video
curl -O -J "http://localhost:8000/download/$JOB_ID"

# 4. Cleanup (optional)
curl -X DELETE "http://localhost:8000/cleanup/$JOB_ID"
```

## Python Client Example

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

# Download processed video
download_response = requests.get(f'http://localhost:8000/download/{job_id}')
with open('edited_video.mp4', 'wb') as f:
    f.write(download_response.content)

print("Video downloaded successfully!")
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
- **Alpine Linux**: Lightweight Docker base image
- **FFmpeg**: Video processing backend

## Project Structure

```
auto-editor-api2/
├── main.py              # FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Multi-stage Alpine build
├── docker-compose.yml  # Docker Compose config
├── .dockerignore       # Docker build exclusions
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
