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
from typing import Optional, List

# VibeHunt Schemas

class Post(BaseModel):
    """
    Posts collection schema
    Collection name: "post"
    """
    title: str = Field(..., description="Idea title")
    description: str = Field(..., description="Short pitch for the idea")
    link: Optional[str] = Field(None, description="Optional external link or prototype URL")
    tags: List[str] = Field(default_factory=list, description="Topic tags")
    author_name: Optional[str] = Field(None, description="Name or handle of the submitter")

class Comment(BaseModel):
    """
    Comments collection schema
    Collection name: "comment"
    """
    post_id: str = Field(..., description="ID of the post this comment belongs to")
    author_name: Optional[str] = Field(None, description="Name or handle of the commenter")
    content: str = Field(..., description="Comment text")

class Vote(BaseModel):
    """
    Votes collection schema
    Collection name: "vote"
    """
    post_id: str = Field(..., description="ID of the post being upvoted")
    client_id: str = Field(..., description="Anonymous client identifier for toggle behavior")

# Example existing schemas (kept for reference but unused by app)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
