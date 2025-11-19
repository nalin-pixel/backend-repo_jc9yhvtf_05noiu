"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional

class Review(BaseModel):
    """
    Reviews for destinations (airport/city)
    Collection name: "review"
    """
    airport_iata: str = Field(..., min_length=3, max_length=3, description="Destination airport IATA code")
    name: str = Field(..., min_length=1, max_length=80, description="Reviewer display name")
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5")
    comment: Optional[str] = Field(None, max_length=1000, description="Review text")
