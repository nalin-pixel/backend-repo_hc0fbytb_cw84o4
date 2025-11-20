"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
Each Pydantic model represents a collection in your database.
Class name lowercased is the collection name (e.g., Listing -> "listing").
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

class Listing(BaseModel):
    """
    Listings collection schema
    Collection name: "listing"
    """
    title: str = Field(..., description="Listing title")
    description: Optional[str] = Field("", description="Detailed description")
    price: float = Field(..., ge=0, description="Price")
    category: str = Field(..., description="Category label")
    city: Optional[str] = Field(None, description="City / locality")
    latitude: Optional[float] = Field(None, description="Latitude")
    longitude: Optional[float] = Field(None, description="Longitude")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    images_hashes: List[str] = Field(default_factory=list, description="Perceptual hashes of images for similarity search")
    seller_name: Optional[str] = Field(None, description="Seller display name")
    seller_email: Optional[EmailStr] = Field(None, description="Seller contact email")
    currency: str = Field("EUR", description="Currency code")
    featured: bool = Field(False, description="Whether featured on home page")
    featured_until: Optional[datetime] = Field(None, description="Feature expiry timestamp")
    quality_score: Optional[int] = Field(None, ge=0, le=100, description="AI-like quality score 0-100")
    quality_feedback: Optional[List[str]] = Field(default_factory=list, description="Tips to improve listing quality")

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user"
    """
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    avatar: Optional[str] = None
    coins: int = Field(0, ge=0)
    admin: bool = False
