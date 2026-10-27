import os
import logging
import shutil
import uuid
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, UploadFile, File, Form, Query, Depends, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import google.generativeai as genai
from dotenv import load_dotenv
import anyio # Import anyio
from PIL import Image

from backend import models, database, schemas, migrate_db

# Load env
load_dotenv()

# Configuration
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3-pro-preview")
LOG_DIR = "backend/logs"
UPLOAD_DIR = "backend/static/uploads"
ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
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

# Run DB Migration (Auto-upgrade schema)
try:
    logger.info("Checking database schema...")
    migrate_db.migrate()
except Exception as e:
    logger.error(f"Database migration failed: {e}")

# Setup DB (Create missing tables)
models.Base.metadata.create_all(bind=database.engine)

# Setup App
app = FastAPI(
    title="Banana Art API",
    description=(
        "Backend API for Banana Art: upload reference images, manage reusable "
        "generation templates, and generate AI images (Gemini) either directly "
        "from a prompt + images, or by applying a saved template."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Increase the default thread pool limit to handle more concurrent background tasks
    # Default is usually 40, we set it to 150 to match DB pool size
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = 150
    logger.info(f"Thread pool limit increased to {limiter.total_tokens}")

# Mount Static
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

# Gemini Setup
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    logger.warning("GEMINI_API_KEY not set in .env")

def generate_image_task(generation_id: int, prompt: str, image_paths: List[str], aspect_ratio: str, db: Session):
    start_time = datetime.now()
    
    # 1. Record Started Time
    gen_record = db.query(models.Generation).filter(models.Generation.id == generation_id).first()
    if gen_record:
        gen_record.started_at = start_time
        db.commit()
        # Calculate Queue Time
        if gen_record.created_at:
             # Make created_at offset-naive for calculation if it's offset-aware, or ensure both match. 
             # SQLAlchemy defaults might be offset-naive. simpler to just use timestamp diff if needed, 
             # but here let's assume both are compatible or standard datetime.
             # Note: SQLite stores as string usually, but SQLAlchemy converts to datetime object.
             # We'll just rely on datetime subtraction.
             try:
                # Ensure timezone info consistency (remove tz info for simple diff if mixed)
                created_at_naive = gen_record.created_at.replace(tzinfo=None)
                start_time_naive = start_time.replace(tzinfo=None)
                queue_duration = (start_time_naive - created_at_naive).total_seconds()
             except:
                queue_duration = 0
    else:
        queue_duration = 0

    logger.info(f"Starting generation for ID {generation_id} with model {MODEL_NAME} (AR: {aspect_ratio}, Images: {len(image_paths)})")
    logger.info(f"Task ID {generation_id} Queue Time: {queue_duration:.2f}s")

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
        
        gemini_start = datetime.now()
        response = model.generate_content(content)
        gemini_end = datetime.now()
        
        exec_duration = (gemini_end - gemini_start).total_seconds()
        logger.info(f"Gemini generation (Execution Time) completed in {exec_duration:.2f} seconds")
        
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
            gen_record.completed_at = datetime.now()
            db.commit()
            
            # Log Final Summary
            total_duration = (gen_record.completed_at.replace(tzinfo=None) - gen_record.created_at.replace(tzinfo=None)).total_seconds()
            logger.info(f"Task ID {generation_id} Finished. Total: {total_duration:.2f}s (Queue: {queue_duration:.2f}s, Exec: {exec_duration:.2f}s)")
            
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        gen_record = db.query(models.Generation).filter(models.Generation.id == generation_id).first()
        if gen_record:
            gen_record.output_image_path = "error"
            gen_record.completed_at = datetime.now()
            db.commit()

def validate_image_upload(file: UploadFile) -> str:
    """Ensure the upload is a real JPEG/PNG/WebP image; return the extension derived from its content."""
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB)")
    try:
        # Restrict decoders so non-image payloads (EPS, SVG, etc.) are never parsed
        with Image.open(file.file, formats=list(ALLOWED_IMAGE_FORMATS)) as img:
            img_format = img.format
            img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG and WebP images are allowed")
    finally:
        file.file.seek(0)
    return ALLOWED_IMAGE_FORMATS[img_format]

def save_uploaded_file(file: UploadFile, db: Session, is_hidden: bool = False) -> models.UploadedImage:
    """Helper to save uploaded file to disk and DB."""
    file_ext = validate_image_upload(file)
    new_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, new_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    db_image = models.UploadedImage(
        filename=file.filename, 
        filepath=f"/static/uploads/{new_filename}",
        is_hidden=is_hidden
    )
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image

@app.post(
    "/api/upload",
    response_model=schemas.UploadedImageOut,
    tags=["Images"],
    summary="Upload an image",
    responses={500: {"model": schemas.ErrorResponse, "description": "Failed to save the uploaded file."}},
    description="Upload a single image file, save it to disk under backend/static/uploads, and store a record for it. The returned image ID can be used in image_ids for /api/generate and /api/templates.",
)
async def upload_image(
    file: UploadFile = File(..., description="Image file to upload (jpg/png/webp, etc.)."),
    db: Session = Depends(database.get_db),
):
    logger.info(f"Receiving upload: {file.filename}")
    try:
        db_image = save_uploaded_file(file, db)
        logger.info(f"Image saved to DB ID: {db_image.id}")
        return db_image
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/api/images",
    response_model=List[schemas.UploadedImageOut],
    tags=["Images"],
    summary="List uploaded images",
    description="List previously uploaded, non-hidden images (newest first). Images uploaded via the 'direct' generation endpoints (is_hidden=true) are excluded so they don't clutter the gallery.",
)
def get_images(
    skip: int = Query(0, description="Number of records to skip (for pagination)."),
    limit: int = Query(100, description="Maximum number of records to return."),
    db: Session = Depends(database.get_db),
):
    # Only return images that are NOT hidden
    images = db.query(models.UploadedImage).filter(models.UploadedImage.is_hidden == False).order_by(models.UploadedImage.upload_time.desc()).offset(skip).limit(limit).all()
    return images

@app.delete(
    "/api/images/{image_id}",
    response_model=schemas.StatusResponse,
    tags=["Images"],
    summary="Delete an uploaded image",
    description="Delete an uploaded image's file from disk and its database record. 404 if the image does not exist.",
    responses={404: {"model": schemas.ErrorResponse, "description": "Image not found."}},
)
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

@app.post(
    "/api/generate",
    response_model=schemas.GenerationOut,
    tags=["Generation"],
    summary="Generate an image from a prompt and previously uploaded images",
    description=(
        "Create a generation request using a raw prompt and zero or more previously-uploaded image IDs "
        "(see POST /api/upload). Generation runs asynchronously in the background; poll "
        "GET /api/generations/{gen_id} until completed_at is set. If generation fails, output_image_path "
        "will be set to the literal string 'error' rather than an HTTP error status, since failures happen "
        "after this endpoint has already returned 200."
    ),
)
async def generate_content(
    prompt: str = Form(..., description="Text description of the desired image. May reference images positionally, e.g. 'Image 1', 'Image 2'."),
    image_ids: List[int] = Form([], description="IDs of uploaded images to use as context. Images are sent to the model in the exact order given here (1st, 2nd, etc.)."),
    aspect_ratio: str = Form("1:1", description="Desired aspect ratio for the output (e.g. '1:1', '4:3', '9:16'). Passed to the model as text guidance."),
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

@app.post(
    "/api/generate-direct",
    response_model=schemas.GenerationOut,
    tags=["Generation"],
    summary="Generate an image from a prompt and raw file uploads",
    description=(
        "Like POST /api/generate, but accepts raw image files instead of image_ids, uploading them in the same "
        "request. Useful for external integrations (e.g. Postman, scripts) that don't already have image IDs. "
        "Uploaded files are marked hidden so they don't appear in GET /api/images."
    ),
    responses={500: {"model": schemas.ErrorResponse, "description": "Failed to save one of the uploaded files."}},
)
async def generate_content_direct(
    prompt: str = Form(..., description="Text description of the desired image."),
    files: List[UploadFile] = File(..., description="Image files to upload and use as context, in the order they should be sent to the model."),
    aspect_ratio: str = Form("1:1", description="Desired aspect ratio for the output (e.g. '1:1', '4:3', '9:16')."),
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
            # Mark these as hidden so they don't clutter the gallery selection
            new_img = save_uploaded_file(file, db, is_hidden=True)
            uploaded_images.append(new_img)
            local_image_paths.append(os.path.join("backend", new_img.filepath.lstrip("/")))
        except HTTPException:
            raise
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
@app.post(
    "/api/templates",
    response_model=schemas.TemplateOut,
    tags=["Templates"],
    summary="Create a template",
    description="Create a reusable generation template: a prompt, an aspect ratio, and a fixed set of reference images (e.g. attire/background) applied every time this template is used via /api/generations/from-template.",
)
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

@app.put(
    "/api/templates/{tmpl_id}",
    response_model=schemas.TemplateOut,
    tags=["Templates"],
    summary="Update a template",
    description="Replace a template's name, prompt, aspect ratio, and reference images. 404 if the template does not exist.",
    responses={404: {"model": schemas.ErrorResponse, "description": "Template not found."}},
)
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

@app.get(
    "/api/templates",
    response_model=List[schemas.TemplateOut],
    tags=["Templates"],
    summary="List templates",
    description="List saved templates.",
)
def get_templates(
    skip: int = Query(0, description="Number of records to skip (for pagination)."),
    limit: int = Query(100, description="Maximum number of records to return."),
    db: Session = Depends(database.get_db),
):
    return db.query(models.Template).offset(skip).limit(limit).all()

@app.delete(
    "/api/templates/{tmpl_id}",
    response_model=schemas.StatusResponse,
    tags=["Templates"],
    summary="Delete a template",
    description="Delete a template's database record. Does not delete the underlying reference images (they may be shared with other templates or generations). 404 if the template does not exist.",
    responses={404: {"model": schemas.ErrorResponse, "description": "Template not found."}},
)
def delete_template(tmpl_id: int, db: Session = Depends(database.get_db)):
    tmpl = db.query(models.Template).filter(models.Template.id == tmpl_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(tmpl)
    db.commit()
    return {"status": "deleted"}

@app.post(
    "/api/generations/from-template",
    response_model=schemas.GenerationOut,
    tags=["Generation"],
    summary="Generate an image by applying a template to previously uploaded images",
    description=(
        "Merge a user's uploaded images with a template's saved prompt, aspect ratio, and reference images, "
        "then generate. The template's prompt_template is used verbatim (not the request body). Generation runs "
        "asynchronously in the background; poll GET /api/generations/{gen_id} until completed_at is set."
    ),
    responses={404: {"model": schemas.ErrorResponse, "description": "Template not found."}},
)
async def generate_from_template(
    template_id: int = Form(..., description="ID of the template to apply (see GET /api/templates)."),
    image_ids: List[int] = Form([], description="IDs of the user's uploaded images (e.g. identity photos). Sent to the model first, in this order, followed by the template's own reference images."),
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

@app.post(
    "/api/generations/from-template-direct",
    response_model=schemas.GenerationOut,
    tags=["Generation"],
    summary="Generate an image by applying a template to raw file uploads",
    description=(
        "Like POST /api/generations/from-template, but accepts raw image files instead of image_ids, uploading "
        "them in the same request. Uploaded files are marked hidden so they don't appear in GET /api/images."
    ),
    responses={
        404: {"model": schemas.ErrorResponse, "description": "Template not found."},
        500: {"model": schemas.ErrorResponse, "description": "Failed to save one of the uploaded files."},
    },
)
async def generate_from_template_direct(
    template_id: int = Form(..., description="ID of the template to apply (see GET /api/templates)."),
    files: List[UploadFile] = File(..., description="User's content image files (e.g. identity photos), in the order they should be sent to the model. Template reference images are appended after these."),
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
            # Mark these as hidden so they don't clutter the gallery selection
            new_img = save_uploaded_file(file, db, is_hidden=True)
            all_source_images.append(new_img)
            local_image_paths.append(os.path.join("backend", new_img.filepath.lstrip("/")))
        except HTTPException:
            raise
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

@app.get(
    "/api/history",
    response_model=schemas.HistoryResponse,
    tags=["History"],
    summary="Search and list generation history",
    description="List generation records (newest first), with optional filtering by ID, prompt substring, and creation date range. Returns a total count alongside the current page for building pagination controls.",
)
def get_history(
    skip: int = Query(0, description="Number of records to skip (for pagination)."),
    limit: int = Query(100, description="Maximum number of records to return."),
    search_id: Optional[int] = Query(None, description="Return only the generation with this exact ID."),
    search_prompt: Optional[str] = Query(None, description="Case-sensitive substring match against the generation's prompt text."),
    start_date: Optional[str] = Query(None, description="Only include generations created at/after this local (UTC+8) date. Accepts 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM'."),
    end_date: Optional[str] = Query(None, description="Only include generations created at/before this local (UTC+8) date. Accepts 'YYYY-MM-DD' (end of day) or 'YYYY-MM-DDTHH:MM'."),
    db: Session = Depends(database.get_db)
):
    query = db.query(models.Generation)
    
    if search_id:
        query = query.filter(models.Generation.id == search_id)
        
    if search_prompt:
        query = query.filter(models.Generation.prompt.contains(search_prompt))
        
    if start_date:
        try:
            if "T" in start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
            else:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            start_dt_utc = start_dt - timedelta(hours=8)
            query = query.filter(models.Generation.created_at >= start_dt_utc)
        except ValueError:
            pass
            
    if end_date:
        try:
            if "T" in end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")
            else:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            end_dt_utc = end_dt - timedelta(hours=8)
            query = query.filter(models.Generation.created_at <= end_dt_utc)
        except ValueError:
            pass

    # Get total count before applying pagination
    total_count = query.count()
    
    history = query.order_by(models.Generation.id.desc()).offset(skip).limit(limit).all()
    
    return {"total": total_count, "items": history}

@app.get(
    "/api/generations/{gen_id}",
    response_model=schemas.GenerationOut,
    tags=["History"],
    summary="Get a single generation record",
    description="Fetch one generation record by ID, including its full source_images list and current status. Poll this after creating a generation to detect completion (completed_at becomes non-null).",
    responses={404: {"model": schemas.ErrorResponse, "description": "Generation not found."}},
)
def get_generation(gen_id: int, db: Session = Depends(database.get_db)):
    gen = db.query(models.Generation).filter(models.Generation.id == gen_id).first()
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")
    return gen

@app.get(
    "/api/generations/{gen_id}/status",
    response_model=schemas.GenerationOut,
    tags=["History"],
    summary="Get a single generation record (alias)",
    description="Alias for GET /api/generations/{gen_id}; returns the exact same generation record. Provided for clients that prefer an explicit '/status' path when polling for completion.",
    responses={404: {"model": schemas.ErrorResponse, "description": "Generation not found."}},
)
def get_generation_status(gen_id: int, db: Session = Depends(database.get_db)):
    return get_generation(gen_id, db)

@app.delete(
    "/api/generations/{gen_id}",
    response_model=schemas.StatusResponse,
    tags=["History"],
    summary="Delete a generation record",
    description="Delete a generation's database record and its generated output file (if any). Does not delete the source images used as input. 404 if the generation does not exist.",
    responses={404: {"model": schemas.ErrorResponse, "description": "Generation not found."}},
)
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

@app.post(
    "/api/client-log",
    response_model=schemas.StatusResponse,
    tags=["System"],
    summary="Forward a frontend log line to the server log",
    description=(
        "Write a client-side log line into the backend's log file (backend/logs/app.log), prefixed with "
        "'[CLIENT LOG]'. Used by the frontend to surface browser-side events/errors in server logs for debugging. "
        "Body shape (not a strict schema, extra/missing keys are tolerated): "
        "`{\"level\": \"INFO\"|\"WARN\"|\"ERROR\", \"message\": string, \"timestamp\": ISO-8601 string}`."
    ),
)
async def client_log(log_data: dict):
    level = log_data.get("level", "INFO")
    message = log_data.get("message", "")
    timestamp = log_data.get("timestamp", "")
    logger.info(f"[CLIENT LOG] {timestamp} [{level}] {message}")
    return {"status": "ok"}
