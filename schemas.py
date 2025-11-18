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
from typing import Optional, Literal, List

# Example schemas (you can keep or remove if not needed)
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Minecraft Donates (Ranks)
class Rank(BaseModel):
    """
    Donation rank/item for the Minecraft server
    Collection name: "rank"
    """
    name: str = Field(..., description="Rank name, e.g., VIP, Premium")
    description: str = Field(..., description="Short description of perks")
    price: float = Field(..., ge=0, description="Price in chosen currency")
    color: str = Field("#f59e0b", description="Primary hex color for UI badge (amber by default)")
    perks: list[str] = Field(default_factory=list, description="List of key perks")
    popular: bool = Field(False, description="Mark as popular for highlighting")
    icon: Optional[str] = Field(None, description="Optional icon name for UI")

class Promo(BaseModel):
    """
    Promo codes with percentage discount
    Collection name: "promo"
    """
    code: str = Field(..., description="Promo code string (uppercase)")
    discount_percent: float = Field(..., ge=0, le=100, description="Discount percentage 0-100")
    active: bool = Field(True, description="Whether promo is active")

class OrderItem(BaseModel):
    rank_id: str = Field(..., description="ID of the rank")
    quantity: int = Field(1, ge=1, description="Quantity of this rank")
    price: float = Field(..., ge=0, description="Unit price at time of purchase")

class Order(BaseModel):
    """
    Order created when a player purchases ranks
    Collection name: "order"
    """
    player: str = Field(..., description="Minecraft nickname")
    items: List[OrderItem] = Field(..., description="Purchased items")
    amount: float = Field(..., ge=0, description="Total amount after discounts")
    currency: str = Field("RUB", description="Currency code (e.g., RUB, USD)")
    status: Literal["pending", "paid", "failed"] = Field("pending", description="Payment status")
    email: Optional[str] = Field(None, description="Contact email (optional)")
    server: Optional[str] = Field(None, description="Server name if multiple")
    promo_code: Optional[str] = Field(None, description="Applied promo code if any")
