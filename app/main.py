from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional
import secrets
import json
from datetime import datetime

from .redis_client import redis_client, get_current_time

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

# Pydantic models
class PasteCreate(BaseModel):
    content: str = Field(..., min_length=1)
    ttl_seconds: Optional[int] = Field(None, ge=1)
    max_views: Optional[int] = Field(None, ge=1)

class PasteResponse(BaseModel):
    id: str
    url: str

# Health check
@app.get("/api/healthz")
async def health_check():
    try:
        redis_client.ping()
        return {"ok": True}
    except:
        return JSONResponse({"ok": False}, status_code=500)

# Create paste
@app.post("/api/pastes", response_model=PasteResponse)
async def create_paste(paste: PasteCreate, request: Request):
    # Generate unique ID
    paste_id = secrets.token_urlsafe(8)
    
    current_time = get_current_time(
        request.headers.get("x-test-now-ms")
    )
    
    # Store paste data
    paste_data = {
        "content": paste.content,
        "created_at": current_time,
        "ttl_seconds": paste.ttl_seconds,
        "max_views": paste.max_views,
        "view_count": 0
    }
    
    redis_client.set(f"paste:{paste_id}", json.dumps(paste_data))
    
    # Set Redis TTL if specified
    if paste.ttl_seconds:
        redis_client.expire(f"paste:{paste_id}", paste.ttl_seconds)
    
    # Generate URL
    base_url = str(request.base_url).rstrip('/')
    url = f"{base_url}/p/{paste_id}"
    
    return {"id": paste_id, "url": url}

# Fetch paste (API)
@app.get("/api/pastes/{paste_id}")
async def get_paste(paste_id: str, request: Request):
    # Get paste from Redis
    paste_json = redis_client.get(f"paste:{paste_id}")
    
    if not paste_json:
        raise HTTPException(status_code=404, detail="Paste not found")
    
    paste = json.loads(paste_json)
    current_time = get_current_time(
        request.headers.get("x-test-now-ms")
    )
    
    # Check TTL expiry
    if paste["ttl_seconds"]:
        expires_at_ms = paste["created_at"] + (paste["ttl_seconds"] * 1000)
        if current_time >= expires_at_ms:
            redis_client.delete(f"paste:{paste_id}")
            raise HTTPException(status_code=404, detail="Paste expired")
    
    # Check view limit
    if paste["max_views"] is not None and paste["view_count"] >= paste["max_views"]:
        raise HTTPException(status_code=404, detail="View limit exceeded")
    
    # Increment view count atomically
    paste["view_count"] += 1
    redis_client.set(f"paste:{paste_id}", json.dumps(paste))
    
    # Calculate remaining views
    remaining_views = None
    if paste["max_views"] is not None:
        remaining_views = paste["max_views"] - paste["view_count"]
    
    # Calculate expires_at
    expires_at = None
    if paste["ttl_seconds"]:
        expires_at_ms = paste["created_at"] + (paste["ttl_seconds"] * 1000)
        expires_at = datetime.fromtimestamp(expires_at_ms / 1000).isoformat() + "Z"
    
    return {
        "content": paste["content"],
        "remaining_views": remaining_views,
        "expires_at": expires_at
    }

# View paste (HTML)
@app.get("/p/{paste_id}", response_class=HTMLResponse)
async def view_paste_html(paste_id: str, request: Request):
    paste_json = redis_client.get(f"paste:{paste_id}")
    
    if not paste_json:
        raise HTTPException(status_code=404, detail="Paste not found")
    
    paste = json.loads(paste_json)
    current_time = get_current_time(None)
    
    # Check expiry
    if paste["ttl_seconds"]:
        expires_at_ms = paste["created_at"] + (paste["ttl_seconds"] * 1000)
        if current_time >= expires_at_ms:
            raise HTTPException(status_code=404, detail="Paste expired")
    
    # Check view limit (don't increment for HTML view)
    if paste["max_views"] is not None and paste["view_count"] >= paste["max_views"]:
        raise HTTPException(status_code=404, detail="View limit exceeded")
    
    return templates.TemplateResponse(
        "view_paste.html",
        {"request": request, "content": paste["content"]}
    )

# Home page (simple form)
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
    <head><title>Pastebin Lite</title></head>
    <body style="font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px;">
        <h1>Pastebin Lite</h1>
        <form id="pasteForm">
            <textarea id="content" placeholder="Enter text..." style="width: 100%; height: 200px; padding: 10px; margin-bottom: 10px;"></textarea><br>
            <input type="number" id="ttl" placeholder="TTL (seconds)" style="width: 45%; padding: 10px; margin-right: 5%;">
            <input type="number" id="maxViews" placeholder="Max views" style="width: 45%; padding: 10px;"><br><br>
            <button type="submit" style="width: 100%; padding: 10px; background: #007bff; color: white; border: none; cursor: pointer;">Create Paste</button>
        </form>
        <div id="result" style="margin-top: 20px;"></div>
        
        <script>
        document.getElementById('pasteForm').onsubmit = async (e) => {
            e.preventDefault();
            const body = { content: document.getElementById('content').value };
            const ttl = document.getElementById('ttl').value;
            const maxViews = document.getElementById('maxViews').value;
            if (ttl) body.ttl_seconds = parseInt(ttl);
            if (maxViews) body.max_views = parseInt(maxViews);
            
            const res = await fetch('/api/pastes', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            const data = await res.json();
            document.getElementById('result').innerHTML = res.ok 
                ? '<p style="color: green;">Paste created! <a href="' + data.url + '" target="_blank">' + data.url + '</a></p>'
                : '<p style="color: red;">Error: ' + data.detail + '</p>';
        };
        </script>
    </body>
    </html>
    """
