"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
Each Pydantic model represents a collection in your database.
Class name lowercased is the collection name (e.g., Listing -> "listing").
"""

from pydantic import BaseModel, Field
from typing import Optional, List

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
    seller_name: Optional[str] = Field(None, description="Seller display name")
    seller_email: Optional[str] = Field(None, description="Seller contact email")
    currency: str = Field("EUR", description="Currency code")
    featured: bool = Field(False, description="Whether featured on home page")
