from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

class UploadedImageBase(BaseModel):
    filename: str = Field(..., description="Original filename as provided by the uploader.", examples=["photo.jpg"])
    filepath: str = Field(..., description="Path to the stored file, relative to the server root (served under /static).", examples=["/static/uploads/aedb838c-eb94-4fc8-bc92-d02a18489cee.png"])


class UploadedImageOut(UploadedImageBase):
    id: int = Field(..., description="Unique identifier of the uploaded image.")
    upload_time: datetime = Field(..., description="Timestamp (UTC) when the image was uploaded.")
    is_hidden: bool = Field(False, description="If true, the image is excluded from the general gallery listing (GET /api/images). Used for images uploaded via the 'direct' generation endpoints so they don't clutter the user's gallery.")

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class TemplateBase(BaseModel):
    name: str = Field(..., description="Display name of the template.", examples=["傳藝test"])
    prompt_template: str = Field(..., description="The prompt text that will be sent to the generation model whenever this template is applied. Should reference reference images positionally (e.g. 'Image 1', 'Image 2') matching the order user images and template images will be merged in.")
    aspect_ratio: str = Field("1:1", description="Output aspect ratio requested from the model when this template is used (e.g. '1:1', '3:4', '9:16'). This is passed to the model as text guidance; it does not crop or resize the reference images themselves.")


class TemplateCreate(TemplateBase):
    reference_image_ids: List[int] = Field(default_factory=list, description="IDs of previously-uploaded images (see POST /api/upload) to attach to this template as fixed reference images (e.g. attire/background references). Order is not guaranteed to be preserved on read.")


class TemplateOut(TemplateBase):
    id: int = Field(..., description="Unique identifier of the template.")
    created_at: datetime = Field(..., description="Timestamp (UTC) when the template was created.")
    reference_images: List[UploadedImageOut] = Field(default_factory=list, description="Full image objects for this template's reference_image_ids.")

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Generations
# ---------------------------------------------------------------------------

class GenerationBase(BaseModel):
    prompt: str = Field(..., description="The full text prompt sent to the generation model.")
    source_image_id: Optional[int] = Field(None, description="ID of the primary/first source image for this generation, kept for backward compatibility with older clients. See source_images for the complete, ordered set.")
    aspect_ratio: Optional[str] = Field("1:1", description="Aspect ratio requested for the output image (e.g. '1:1', '4:3', '9:16').")


class GenerationOut(GenerationBase):
    """
    Represents a generation record at any point in its lifecycle.

    The same shape is returned both immediately after submission (POST endpoints,
    where output_image_path/started_at/completed_at are still null) and when
    polling for status (GET /api/generations/{gen_id}), since generation runs
    asynchronously in a background task rather than blocking the request.
    """
    id: int = Field(..., description="Unique identifier of the generation record.")
    output_image_path: Optional[str] = Field(None, description="Path to the generated output file, relative to the server root (served under /static). Null while the generation is still processing. The literal value 'error' indicates the generation failed.")
    created_at: datetime = Field(..., description="Timestamp (UTC) when the generation request was received/queued.")
    started_at: Optional[datetime] = Field(None, description="Timestamp (UTC) when the background worker started processing this generation. Null while still queued.")
    completed_at: Optional[datetime] = Field(None, description="Timestamp (UTC) when the generation finished (successfully or with an error). Null while still in progress.")
    source_images: List[UploadedImageOut] = Field(default_factory=list, description="All images used as input for this generation, in the exact order they were sent to the model.")

    class Config:
        from_attributes = True


class HistoryResponse(BaseModel):
    total: int = Field(..., description="Total number of generation records matching the query filters, ignoring pagination (skip/limit). Use this to compute page counts.")
    items: List[GenerationOut] = Field(..., description="Page of generation records matching the query filters, ordered newest first.")


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

class StatusResponse(BaseModel):
    status: str = Field(..., description="Result of the operation.", examples=["ok", "deleted"])


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error message.", examples=["Template not found"])
