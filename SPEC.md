## 1 Scope

Build a **Minimal-Viable-Product** that lets an authenticated user:

1. Upload learning materials (any file Pandoc can read).  
2. Receive an extracted / refined topic outline.  
3. Generate Beamer slides **with or without narration**.  
4. (Optionally) receive per-slide audio and a stitched MP4.  

The target: **single - machine deployment**, FastAPI + Uvicorn (4 workers), no message queue, all heavy work off-loaded to ```asyncio.to_thread```.  
Time budget ≈ 2 engineering days.

---

## 2 High-Level Flow

1. ```POST /presentation/upload_materials```  
   • Files cached on disk ≤ 30 min.  
2. ```POST /topics/extract_outline```  
   • LLM reads materials’ plaintext → returns JSON outline.  
3. Client edits / confirms outline.  
4. EITHER  
   a. ```POST /presentation/build_slides``` → PNG URLs  
   b. ```POST /presentation/build_presentation``` → PNG+audio  
5. (Optional) ```POST /presentation/download_video``` → MP4

---

## 3 Authentication

• All endpoints except root and healthcheck require  
  ```Authorization: Bearer <access_token>```  
• Token verified against **Supabase JWKs**.  

Errors  
401 Unauthenticated  • header missing  
403 Forbidden        • token invalid / expired

---

## 4 REST Endpoints

### 4.1 Materials

| Method | Path | Body | Success (200) | Errors |
|---|---|---|---|---|
| POST | ```/presentation/upload_materials``` | ```multipart/form-data``` files[] | ```{ "keys": ["uuid_name.pdf", …] }``` | 400 too many / too large |

Limits  
• ```MAX_ATTACHMENTS``` = 5  
• ```MAX_ATTACHMENT_SIZE_MB``` = 100  

Files stored in ```settings.materials_dir/uuid_filename.ext```.

---

### 4.2 Outline Extraction

```http
POST /topics/extract_outline
```

Request body  
```json
{
  "material_keys": ["uuid_name.pdf", …]
}
```

Response (200)  
```json
{
  "outline": [
    { "topic": "…", "subtopics": ["…", "…"] },
    …
  ],
  "unsupported_attachments": ["badfile.xyz"]
}
```

Errors  
• 404 material not found

---

### 4.3 Slide Generation – PNG‐Only

```http
POST /presentation/build_slides
```

Body  
```json
{ "outline": [ { "topic": "...", "subtopics": ["..."] } ] }
```

Returns ordered list of PNG URLs:  

```json
[
  "/pngs/slide_1.png",
  "/pngs/slide_2.png"
]
```

---

### 4.4 Slide + Audio Generation

```http
POST /presentation/build_presentation
```

Body  
```json
{
  "outline": [ {...} ],
  "voice": "en-US-Standard-C"   // optional, defaults cfg
}
```

Response  
```json
[
  {
    "slide_png_url": "/pngs/slide_1.png",
    "audio_url": "/audios/slide_1.mp3"
  },
  …
]
```

---

### 4.5 Voice Preview

```POST /presentation/sample_voice``` → ```{ "audio_url": "…" }```

---

### 4.6 Video Stitching

```POST /presentation/download_video``` → returns ```video/mp4``` file.  
Prerequisite: build_presentation already called in same session.

---

### 4.7 Auxiliary

* ```GET /healthz``` – returns ```{ "ok": true }```  
* ```GET /version``` – git commit hash & build date

---

## 5 Background Processing

| Task | Implementation |
|---|---|
| Pandoc convert → PDF | ```asyncio.to_thread(subprocess.run)``` |
| LaTeX compile → PDF | same |
| PDF → PNG | ```pdftoppm``` |
| Kokoro TTS | async HTTP |
| FFMPEG mux | off-thread call |

All intermediate artefacts live under ```/tmp/panic_prep/{pdfs,pngs,audios,videos}``` and are auto-purged by a cron every 30 min.

---

## 6 Prompt Files

Located in ```prompts/``` (plain text templates):

1. ```materials_extraction.prompt```  
2. ```beamer_generator.prompt```  
3. ```narration_generator.prompt```  
4. ```topic_list_generator.prompt``` (fallback)  

Placeholders use ```{variable}``` syntax.

---

## 7 Configuration (see ```src/config.py```)

Environment variables (dotenv):

```
SUPABASE_URL, SUPABASE_JWK_URL, SUPABASE_SERVICE_KEY
KOKORO_API_KEY, KOKORO_VOICE_DEFAULT
MAX_ATTACHMENTS, MAX_ATTACHMENT_SIZE_MB, MAX_GEN_PER_DAY
FFMPEG_PATH, PDFTOPPM_PATH
UVICORN_WORKERS, LOG_LEVEL
```

Default workspace ```/tmp/panic_prep``` is auto-created.

---

## 8 Error Codes (non-auth)

| Code | Meaning |
|---|---|
| 400 | bad request / limit exceeded |
| 404 | referenced material not found |
| 422 | outline malformed |
| 429 | per-user generation cap reached |
| 500 | internal – uncaught error |

---

## 9 Concurrency & Scaling

* Uvicorn started with ```--workers $UVICORN_WORKERS``` (default 4).  
* CPU-heavy subprocesses run in background threads, so requests remain non-blocking.  
* No queue for MVP; consider Celery + Redis after day 2.

---

## 10 Security Notes

* Materials directory is **not publicly browsable**; only explicit StaticFiles mounts (```/materials/…```, ```/pngs/…```, etc.) expose generated artefacts.  
* Artefact filenames are UUID-prefixed to prevent guessing.  
* Artefacts older than 30 min removed by ```cleanup.py``` (cron or APScheduler job).  

