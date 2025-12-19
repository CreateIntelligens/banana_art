import os
import logging
import shutil
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import google.generativeai as genai
from dotenv import load_dotenv

from backend import models, database, schemas

# Load env
load_dotenv()

# Configuration
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3-pro-preview")
LOG_DIR = "backend/logs"
UPLOAD_DIR = "backend/static/uploads"
GENERATED_DIR = "backend/static/generated"

# Setup Logging
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Setup DB
models.Base.metadata.create_all(bind=database.engine)

# Setup App
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

# Gemini Setup
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    logger.warning("GEMINI_API_KEY not set in .env")

def generate_image_task(generation_id: int, prompt: str, image_path: Optional[str], aspect_ratio: str, db: Session):
    logger.info(f"Starting generation for ID {generation_id} with model {MODEL_NAME} (AR: {aspect_ratio})")
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Enhance prompt with aspect ratio as fallback
        enhanced_prompt = f"{prompt}, aspect ratio {aspect_ratio}"
        content = [enhanced_prompt]

        if image_path:
             sample_file = genai.upload_file(image_path, mime_type="image/jpeg")
             content.append(sample_file)
        
        response = model.generate_content(content)
        
        output_path_for_db = None
        generated_text = ""
        
        # Handle response parts
        if response.parts:
            for part in response.parts:
                if part.text:
                    generated_text += part.text
                    logger.info(f"Gemini text part: {part.text[:50]}...")
                
                if part.inline_data:
                    logger.info(f"Gemini received inline_data ({part.inline_data.mime_type})")
                    # It's an image or blob
                    mime_type = part.inline_data.mime_type
                    ext = ".png"
                    if "jpeg" in mime_type or "jpg" in mime_type: ext = ".jpg"
                    if "webp" in mime_type: ext = ".webp"
                    
                    filename = f"gen_{uuid.uuid4()}{ext}"
                    filepath = os.path.join(GENERATED_DIR, filename)
                    
                    with open(filepath, "wb") as f:
                        f.write(part.inline_data.data)
                    
                    # Prioritize image for DB display
                    output_path_for_db = f"/static/generated/{filename}"

        # If no image found but we have text, save text
        if not output_path_for_db and generated_text:
            filename = f"gen_{uuid.uuid4()}.txt"
            filepath = os.path.join(GENERATED_DIR, filename)
            with open(filepath, "w") as f:
                f.write(generated_text)
            output_path_for_db = f"/static/generated/{filename}"
            
        if not output_path_for_db:
             # Fallback if response.text works (sometimes parts is empty but text property works for simple text)
             try:
                 if response.text:
                     filename = f"gen_{uuid.uuid4()}.txt"
                     filepath = os.path.join(GENERATED_DIR, filename)
                     with open(filepath, "w") as f:
                         f.write(response.text)
                     output_path_for_db = f"/static/generated/{filename}"
             except:
                 pass

        if not output_path_for_db:
            output_path_for_db = "error"
            logger.error("No valid output (text or image) extracted from Gemini response")

        # Update DB
        gen_record = db.query(models.Generation).filter(models.Generation.id == generation_id).first()
        if gen_record:
            gen_record.output_image_path = output_path_for_db
            db.commit()
            
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        gen_record = db.query(models.Generation).filter(models.Generation.id == generation_id).first()
        if gen_record:
            gen_record.output_image_path = "error"
            db.commit()


@app.post("/api/upload", response_model=schemas.UploadedImage)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    logger.info(f"Receiving upload: {file.filename}")
    try:
        file_ext = os.path.splitext(file.filename)[1]
        new_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, new_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        db_image = models.UploadedImage(filename=file.filename, filepath=f"/static/uploads/{new_filename}")
        db.add(db_image)
        db.commit()
        db.refresh(db_image)
        
        logger.info(f"Image saved to {file_path}, ID: {db_image.id}")
        return db_image
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/images", response_model=List[schemas.UploadedImage])
def get_images(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    images = db.query(models.UploadedImage).order_by(models.UploadedImage.upload_time.desc()).offset(skip).limit(limit).all()
    return images

@app.post("/api/generate", response_model=schemas.Generation)
async def generate_content(
    prompt: str = Form(...), 
    image_id: Optional[int] = Form(None), 
    aspect_ratio: str = Form("1:1"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(database.get_db)
):
    logger.info(f"Generation request: Prompt='{prompt}', ImageID={image_id}, AR={aspect_ratio}")
    
    local_image_path = None
    
    if image_id:
        # Verify image exists
        image = db.query(models.UploadedImage).filter(models.UploadedImage.id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        local_image_path = os.path.join("backend", image.filepath.lstrip("/"))
        
    # Create Generation Record (Pending)
    db_gen = models.Generation(prompt=prompt, source_image_id=image_id, aspect_ratio=aspect_ratio)
    db.add(db_gen)
    db.commit()
    db.refresh(db_gen)
    
    # Start Background Task
    background_tasks.add_task(generate_image_task, db_gen.id, prompt, local_image_path, aspect_ratio, db)
    
    return db_gen

@app.get("/api/history", response_model=List[schemas.Generation])
def get_history(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    history = db.query(models.Generation).order_by(models.Generation.created_at.desc()).offset(skip).limit(limit).all()
    return history

@app.get("/api/generations/{gen_id}", response_model=schemas.Generation)
def get_generation(gen_id: int, db: Session = Depends(database.get_db)):
    gen = db.query(models.Generation).filter(models.Generation.id == gen_id).first()
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")
    return gen

@app.delete("/api/generations/{gen_id}")
def delete_generation(gen_id: int, db: Session = Depends(database.get_db)):
    gen = db.query(models.Generation).filter(models.Generation.id == gen_id).first()
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")
    
    # Optional: Delete the actual file if you want to save space
    # For now we only delete the DB record as requested, keeping "original" (source) images safe.
    # If "original picture retained" means the SOURCE image, we are safe.
    # If we want to delete the GENERATED file:
    if gen.output_image_path and gen.output_image_path != "error" and not gen.output_image_path.endswith(".txt"):
         # Construct local path from url
         # /static/generated/filename -> backend/static/generated/filename
         local_path = os.path.join("backend", gen.output_image_path.lstrip("/"))
         if os.path.exists(local_path):
             try:
                 os.remove(local_path)
             except Exception as e:
                 logger.error(f"Failed to remove file {local_path}: {e}")

    db.delete(gen)
    db.commit()
    return {"status": "deleted"}

@app.post("/api/client-log")
async def client_log(log_data: dict):
    level = log_data.get("level", "INFO")
    message = log_data.get("message", "")
    timestamp = log_data.get("timestamp", "")
    logger.info(f"[CLIENT LOG] {timestamp} [{level}] {message}")
    return {"status": "ok"}