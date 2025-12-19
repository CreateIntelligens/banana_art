from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class UploadedImageBase(BaseModel):
    filename: str
    filepath: str

class UploadedImage(UploadedImageBase):
    id: int
    upload_time: datetime

    class Config:
        from_attributes = True

class GenerationBase(BaseModel):
    prompt: str
    source_image_id: Optional[int] = None
    aspect_ratio: Optional[str] = "1:1"

class Generation(GenerationBase):
    id: int
    output_image_path: Optional[str] = None
    created_at: datetime
    source_image: Optional[UploadedImage] = None

    class Config:
        from_attributes = True
