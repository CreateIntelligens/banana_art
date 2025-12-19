from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class UploadedImage(Base):
    __tablename__ = "uploaded_images"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    filepath = Column(String) # Path relative to backend/static or full path
    upload_time = Column(DateTime(timezone=True), server_default=func.now())
    
    generations = relationship("Generation", back_populates="source_image")

class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True, index=True)
    prompt = Column(Text)
    source_image_id = Column(Integer, ForeignKey("uploaded_images.id"), nullable=True)
    aspect_ratio = Column(String, default="1:1")
    output_image_path = Column(String, nullable=True) # Path to generated image
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source_image = relationship("UploadedImage", back_populates="generations")
