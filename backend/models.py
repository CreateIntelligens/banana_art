from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Table, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

# Association Table for Generation Inputs (Many-to-Many)
generation_inputs = Table(
    'generation_inputs',
    Base.metadata,
    Column('generation_id', Integer, ForeignKey('generations.id')),
    Column('uploaded_image_id', Integer, ForeignKey('uploaded_images.id'))
)

# Association Table for Template Inputs (Many-to-Many)
template_inputs = Table(
    'template_inputs',
    Base.metadata,
    Column('template_id', Integer, ForeignKey('templates.id')),
    Column('uploaded_image_id', Integer, ForeignKey('uploaded_images.id'))
)

class UploadedImage(Base):
    __tablename__ = "uploaded_images"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    filepath = Column(String) # Path relative to backend/static or full path
    upload_time = Column(DateTime(timezone=True), server_default=func.now())
    is_hidden = Column(Boolean, default=False)
    
    generations = relationship("Generation", secondary=generation_inputs, back_populates="source_images")
    templates = relationship("Template", secondary=template_inputs, back_populates="reference_images")

class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    prompt_template = Column(Text) # The predefined prompt
    aspect_ratio = Column(String, default="1:1") # Added field
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Reference images for the style
    reference_images = relationship("UploadedImage", secondary=template_inputs, back_populates="templates")

class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True, index=True)
    prompt = Column(Text)
    
    # Keeping this for backward compatibility or primary thumb
    source_image_id = Column(Integer, ForeignKey("uploaded_images.id"), nullable=True)
    
    aspect_ratio = Column(String, default="1:1")
    output_image_path = Column(String, nullable=True) # Path to generated image
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Many-to-Many relationship
    source_images = relationship("UploadedImage", secondary=generation_inputs, back_populates="generations")