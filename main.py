import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Rank as RankSchema, Order as OrderSchema

app = FastAPI(title="Minecraft Autodonate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Helpers ---------
class ObjectIdStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        # accept strings
        try:
            ObjectId(str(v))
        except Exception:
            raise ValueError("Invalid ObjectId")
        return str(v)

def serialize_doc(doc: dict):
    if not doc:
        return doc
    d = {**doc}
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # convert nested ObjectIds if any
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d

# --------- API Models ---------
class CreateRank(BaseModel):
    name: str
    description: str
    price: float = Field(ge=0)
    color: str = "#22d3ee"
    perks: List[str] = []
    popular: bool = False
    icon: Optional[str] = None

class RankResponse(CreateRank):
    id: ObjectIdStr

class CreateOrder(BaseModel):
    player: str = Field(..., description="Minecraft nickname")
    rank_id: str = Field(..., description="Rank ID")
    email: Optional[str] = None
    server: Optional[str] = None

class OrderResponse(BaseModel):
    id: ObjectIdStr
    player: str
    rank_id: str
    amount: float
    currency: str = "RUB"
    status: str
    email: Optional[str] = None
    server: Optional[str] = None

# --------- Routes ---------
@app.get("/")
def root():
    return {"message": "Minecraft Autodonate Backend Running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response

# Ranks
@app.get("/api/ranks", response_model=List[RankResponse])
def list_ranks(limit: Optional[int] = None):
    docs = get_documents("rank", {}, limit)
    return [RankResponse(**serialize_doc(d)) for d in docs]

@app.post("/api/ranks", response_model=RankResponse)
def create_rank(payload: CreateRank):
    # validate with schema
    schema = RankSchema(**payload.model_dump())
    new_id = create_document("rank", schema)
    doc = db["rank"].find_one({"_id": ObjectId(new_id)})
    return RankResponse(**serialize_doc(doc))

@app.post("/api/ranks/seed")
def seed_ranks():
    if db["rank"].count_documents({}) > 0:
        return {"message": "Ranks already exist"}
    defaults = [
        {
            "name": "VIP",
            "description": "Стартовый донат с базовыми привилегиями",
            "price": 149,
            "color": "#10b981",
            "perks": [
                "/kit vip",
                "+2 сетхомы",
                "Ежедневный бонус",
            ],
            "popular": False,
            "icon": "Star"
        },
        {
            "name": "Premium",
            "description": "Расширенные возможности и бонусы",
            "price": 299,
            "color": "#3b82f6",
            "perks": [
                "/repair",
                "+5 сетхомов",
                "Цветной чат",
            ],
            "popular": True,
            "icon": "Crown"
        },
        {
            "name": "Deluxe",
            "description": "Максимальные привилегии для истинных ценителей",
            "price": 599,
            "color": "#f59e0b",
            "perks": [
                "/fly",
                "+10 сетхомов",
                "Эффекты и частицы",
            ],
            "popular": False,
            "icon": "Gem"
        },
    ]
    for d in defaults:
        schema = RankSchema(**d)
        create_document("rank", schema)
    return {"message": "Seeded"}

# Orders
@app.post("/api/orders", response_model=OrderResponse)
def create_order(payload: CreateOrder):
    # validate rank exists
    try:
        rank = db["rank"].find_one({"_id": ObjectId(payload.rank_id)})
    except Exception:
        rank = None
    if not rank:
        raise HTTPException(status_code=404, detail="Rank not found")

    order_data = OrderSchema(
        player=payload.player,
        rank_id=str(rank["_id"]),
        amount=float(rank.get("price", 0)),
        currency="RUB",
        status="pending",
        email=payload.email,
        server=payload.server,
    )
    new_id = create_document("order", order_data)
    doc = db["order"].find_one({"_id": ObjectId(new_id)})
    return OrderResponse(**serialize_doc(doc))

@app.post("/api/orders/{order_id}/pay", response_model=OrderResponse)
def simulate_pay(order_id: str):
    # Simulate payment success and mark as paid
    try:
        _id = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order id")
    res = db["order"].find_one_and_update(
        {"_id": _id},
        {"$set": {"status": "paid"}},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse(**serialize_doc(res))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
