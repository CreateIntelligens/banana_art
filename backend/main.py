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

def generate_image_task(generation_id: int, prompt: str, image_paths: List[str], aspect_ratio: str, db: Session):
    logger.info(f"Starting generation for ID {generation_id} with model {MODEL_NAME} (AR: {aspect_ratio}, Images: {len(image_paths)})")
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Enhance prompt with aspect ratio as fallback
        enhanced_prompt = f"{prompt}, aspect ratio {aspect_ratio}"
        content = [enhanced_prompt]

        for path in image_paths:
             try:
                 # Ensure we have absolute path or correct relative path
                 # The path comes from DB as "backend/static/..." (relative to root) or absolute
                 sample_file = genai.upload_file(path, mime_type="image/jpeg")
                 content.append(sample_file)
             except Exception as file_err:
                 logger.error(f"Failed to upload file to Gemini {path}: {file_err}")
        
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

def save_uploaded_file(file: UploadFile, db: Session) -> models.UploadedImage:
    """Helper to save uploaded file to disk and DB."""
    file_ext = os.path.splitext(file.filename)[1]
    new_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, new_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    db_image = models.UploadedImage(filename=file.filename, filepath=f"/static/uploads/{new_filename}")
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image

@app.post("/api/upload", response_model=schemas.UploadedImage)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    logger.info(f"Receiving upload: {file.filename}")
    try:
        db_image = save_uploaded_file(file, db)
        logger.info(f"Image saved to DB ID: {db_image.id}")
        return db_image
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/images", response_model=List[schemas.UploadedImage])
def get_images(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    images = db.query(models.UploadedImage).order_by(models.UploadedImage.upload_time.desc()).offset(skip).limit(limit).all()
    return images

@app.delete("/api/images/{image_id}")
def delete_image(image_id: int, db: Session = Depends(database.get_db)):
    image = db.query(models.UploadedImage).filter(models.UploadedImage.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Remove from filesystem
    local_path = os.path.join("backend", image.filepath.lstrip("/"))
    if os.path.exists(local_path):
        try:
            os.remove(local_path)
        except Exception as e:
            logger.error(f"Failed to remove file {local_path}: {e}")

    db.delete(image)
    db.commit()
    return {"status": "deleted"}

@app.post("/api/generate", response_model=schemas.Generation)
async def generate_content(
    prompt: str = Form(...), 
    image_ids: List[int] = Form([]),
    aspect_ratio: str = Form("1:1"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(database.get_db)
):
    """
    Generate content using Gemini model.
    
    - **prompt**: Text description of the desired image.
    - **image_ids**: List of uploaded image IDs to be used as context. 
      **Ordering**: Images are sent to the model in the exact order they are provided in this list (1st, 2nd, etc.).
    - **aspect_ratio**: Desired aspect ratio for the output (e.g., "1:1", "16:9").
    """
    logger.info(f"Generation request: Prompt='{prompt}', ImageIDs={image_ids}, AR={aspect_ratio}")
    
    local_image_paths = []
    
    # 1. Fetch images from DB
    uploaded_images = []
    if image_ids:
        raw_images = db.query(models.UploadedImage).filter(models.UploadedImage.id.in_(image_ids)).all()
        img_map = {img.id: img for img in raw_images}
        
        # Sort uploaded_images list by input order for DB relationship
        for mid in image_ids:
            if mid in img_map:
                uploaded_images.append(img_map[mid])
                local_image_paths.append(os.path.join("backend", img_map[mid].filepath.lstrip("/")))
            
    # 2. Create Generation Record
    db_gen = models.Generation(prompt=prompt, aspect_ratio=aspect_ratio)
    
    # Set Primary Source Image (for backward compat)
    if uploaded_images:
        db_gen.source_image_id = uploaded_images[0].id
        
    # Set Many-to-Many Relationship
    db_gen.source_images = uploaded_images
    
    db.add(db_gen)
    db.commit()
    db.refresh(db_gen)
    
    # 3. Start Background Task
    background_tasks.add_task(generate_image_task, db_gen.id, prompt, local_image_paths, aspect_ratio, db)
    
    return db_gen

@app.post("/api/generate-direct", response_model=schemas.Generation)
async def generate_content_direct(
    prompt: str = Form(...), 
    files: List[UploadFile] = File(...),
    aspect_ratio: str = Form("1:1"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(database.get_db)
):
    """
    Direct generation endpoint that accepts image files instead of IDs.
    Useful for external integrations (e.g., Postman, Scripts).
    
    - **prompt**: Text description.
    - **files**: List of image files to upload and use.
    - **aspect_ratio**: Output aspect ratio.
    """
    logger.info(f"Direct generation request: Prompt='{prompt}', Files={len(files)}, AR={aspect_ratio}")
    
    uploaded_images = []
    local_image_paths = []
    
    # Process file uploads
    for file in files:
        try:
            new_img = save_uploaded_file(file, db)
            uploaded_images.append(new_img)
            local_image_paths.append(os.path.join("backend", new_img.filepath.lstrip("/")))
        except Exception as e:
            logger.error(f"Failed to process uploaded file in direct generate: {e}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    # Create Generation Record
    db_gen = models.Generation(prompt=prompt, aspect_ratio=aspect_ratio)
    if uploaded_images:
        db_gen.source_image_id = uploaded_images[0].id
    db_gen.source_images = uploaded_images
    
    db.add(db_gen)
    db.commit()
    db.refresh(db_gen)
    
    background_tasks.add_task(generate_image_task, db_gen.id, prompt, local_image_paths, aspect_ratio, db)
    return db_gen

# Template APIs
@app.post("/api/templates", response_model=schemas.Template)
def create_template(
    template: schemas.TemplateCreate,
    db: Session = Depends(database.get_db)
):
    db_template = models.Template(name=template.name, prompt_template=template.prompt_template, aspect_ratio=template.aspect_ratio)
    
    if template.reference_image_ids:
        imgs = db.query(models.UploadedImage).filter(models.UploadedImage.id.in_(template.reference_image_ids)).all()
        db_template.reference_images = imgs
        
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template

@app.put("/api/templates/{tmpl_id}", response_model=schemas.Template)
def update_template(
    tmpl_id: int,
    template: schemas.TemplateCreate,
    db: Session = Depends(database.get_db)
):
    db_template = db.query(models.Template).filter(models.Template.id == tmpl_id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    db_template.name = template.name
    db_template.prompt_template = template.prompt_template
    db_template.aspect_ratio = template.aspect_ratio
    
    if template.reference_image_ids is not None:
        imgs = db.query(models.UploadedImage).filter(models.UploadedImage.id.in_(template.reference_image_ids)).all()
        db_template.reference_images = imgs
        
    db.commit()
    db.refresh(db_template)
    return db_template

@app.get("/api/templates", response_model=List[schemas.Template])
def get_templates(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Template).offset(skip).limit(limit).all()

@app.delete("/api/templates/{tmpl_id}")
def delete_template(tmpl_id: int, db: Session = Depends(database.get_db)):
    tmpl = db.query(models.Template).filter(models.Template.id == tmpl_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(tmpl)
    db.commit()
    return {"status": "deleted"}

@app.post("/api/generations/from-template", response_model=schemas.Generation)
async def generate_from_template(
    template_id: int = Form(...),
    image_ids: List[int] = Form([]), # User's content images
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(database.get_db)
):
    """
    Generate content by applying a saved template to user-selected images.

    - **template_id**: ID of the template to apply.
    - **image_ids**: List of user-selected image IDs.
    
    **Image Ordering Logic**:
    The model receives images in the following order:
    1. **User Images**: The images selected by the user (in the order provided in `image_ids`).
    2. **Template Images**: The reference images associated with the template.
    
    Example: User selects [ImgA, ImgB] and Template has [ImgT]. Model input order: [ImgA, ImgB, ImgT].
    """
    logger.info(f"Template generation: TemplateID={template_id}, UserImageIDs={image_ids}")

    # 1. Fetch Template
    template = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # 2. Prepare all image sources
    all_source_images = []
    local_image_paths = []
    
    # Add user images first
    if image_ids:
        user_images = db.query(models.UploadedImage).filter(models.UploadedImage.id.in_(image_ids)).all()
        img_map = {img.id: img for img in user_images}
        for mid in image_ids:
            if mid in img_map:
                all_source_images.append(img_map[mid])
                local_image_paths.append(os.path.join("backend", img_map[mid].filepath.lstrip("/")))
    
    # Add template reference images
    for tmpl_img in template.reference_images:
        if tmpl_img not in all_source_images: # Avoid duplicates
            all_source_images.append(tmpl_img)
            local_image_paths.append(os.path.join("backend", tmpl_img.filepath.lstrip("/")))

    # 3. Create Generation Record
    db_gen = models.Generation(
        prompt=template.prompt_template, # Use template's prompt directly
        aspect_ratio=template.aspect_ratio,
        source_images=all_source_images
    )
    if all_source_images:
        db_gen.source_image_id = all_source_images[0].id
        
    db.add(db_gen)
    db.commit()
    db.refresh(db_gen)

    # 4. Start Background Task
    background_tasks.add_task(
        generate_image_task,
        db_gen.id,
        template.prompt_template,
        local_image_paths,
        template.aspect_ratio,
        db
    )
    
    return db_gen

@app.post("/api/generations/from-template-direct", response_model=schemas.Generation)
async def generate_from_template_direct(
    template_id: int = Form(...),
    files: List[UploadFile] = File(...), # User's content images (Direct Upload)
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(database.get_db)
):
    """
    Direct template generation endpoint that accepts image files.
    
    - **template_id**: ID of the template.
    - **files**: List of image files to upload and use as User Images.
    
    **Order**: User Files -> Template Images.
    """
    logger.info(f"Direct template generation: TemplateID={template_id}, Files={len(files)}")

    # 1. Fetch Template
    template = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    all_source_images = []
    local_image_paths = []
    
    # 2. Process User Files
    for file in files:
        try:
            new_img = save_uploaded_file(file, db)
            all_source_images.append(new_img)
            local_image_paths.append(os.path.join("backend", new_img.filepath.lstrip("/")))
        except Exception as e:
            logger.error(f"Failed to process uploaded file in direct template gen: {e}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    # 3. Add Template Images
    for tmpl_img in template.reference_images:
        # Note: We don't check for duplicates here as freshly uploaded files definitely have different IDs
        all_source_images.append(tmpl_img)
        local_image_paths.append(os.path.join("backend", tmpl_img.filepath.lstrip("/")))

    # 4. Create Generation Record
    db_gen = models.Generation(
        prompt=template.prompt_template,
        aspect_ratio=template.aspect_ratio,
        source_images=all_source_images
    )
    if all_source_images:
        db_gen.source_image_id = all_source_images[0].id
        
    db.add(db_gen)
    db.commit()
    db.refresh(db_gen)

    background_tasks.add_task(
        generate_image_task,
        db_gen.id,
        template.prompt_template,
        local_image_paths,
        template.aspect_ratio,
        db
    )
    
    return db_gen

# ... other endpoints ...

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
    
    if gen.output_image_path and gen.output_image_path != "error" and not gen.output_image_path.endswith(".txt"):
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
