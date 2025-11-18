import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Rank as RankSchema, Order as OrderSchema, Promo as PromoSchema

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
    color: str = "#f59e0b"  # amber default
    perks: List[str] = []
    popular: bool = False
    icon: Optional[str] = None

class RankResponse(CreateRank):
    id: ObjectIdStr

class CartItem(BaseModel):
    rank_id: str
    quantity: int = Field(1, ge=1)

class CreateOrder(BaseModel):
    player: str = Field(..., description="Minecraft nickname")
    items: List[CartItem]
    email: Optional[str] = None
    server: Optional[str] = None
    promo_code: Optional[str] = None

class OrderItemResponse(BaseModel):
    rank_id: str
    quantity: int
    price: float

class OrderResponse(BaseModel):
    id: ObjectIdStr
    player: str
    items: List[OrderItemResponse]
    amount: float
    currency: str = "RUB"
    status: str
    email: Optional[str] = None
    server: Optional[str] = None
    promo_code: Optional[str] = None

class PromoResponse(BaseModel):
    code: str
    discount_percent: float
    active: bool

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
            "color": "#b45309",  # amber-700
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
            "color": "#d97706",  # amber-600
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
            "color": "#f59e0b",  # amber-500
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
    # seed a demo promo
    if db["promo"].count_documents({"code": "START"}) == 0:
        create_document("promo", PromoSchema(code="START", discount_percent=10, active=True))
    return {"message": "Seeded"}

# Promos
@app.get("/api/promos/{code}", response_model=PromoResponse)
def get_promo(code: str):
    doc = db["promo"].find_one({"code": code.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="Promo not found")
    d = serialize_doc(doc)
    return PromoResponse(code=d.get("code", code.upper()), discount_percent=d.get("discount_percent", 0.0), active=d.get("active", False))

@app.post("/api/promos")
def create_promo(payload: PromoSchema):
    new_id = create_document("promo", payload)
    doc = db["promo"].find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)

# Orders
@app.post("/api/orders", response_model=OrderResponse)
def create_order(payload: CreateOrder):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # build items with prices and compute total
    items_resp = []
    total = 0.0
    for it in payload.items:
        try:
            rank = db["rank"].find_one({"_id": ObjectId(it.rank_id)})
        except Exception:
            rank = None
        if not rank:
            raise HTTPException(status_code=404, detail=f"Rank not found: {it.rank_id}")
        price = float(rank.get("price", 0))
        items_resp.append({"rank_id": str(rank["_id"]), "quantity": it.quantity, "price": price})
        total += price * it.quantity

    applied_promo = None
    if payload.promo_code:
        promo = db["promo"].find_one({"code": payload.promo_code.upper(), "active": True})
        if promo:
            applied_promo = promo
            discount_percent = float(promo.get("discount_percent", 0))
            total = round(total * (1 - discount_percent / 100.0), 2)
        else:
            # ignore invalid promo silently or raise?
            raise HTTPException(status_code=404, detail="Promo not found or inactive")

    order_data = OrderSchema(
        player=payload.player,
        items=[
            {
                "rank_id": it["rank_id"],
                "quantity": it["quantity"],
                "price": it["price"],
            }
            for it in items_resp
        ],
        amount=total,
        currency="RUB",
        status="pending",
        email=payload.email,
        server=payload.server,
        promo_code=payload.promo_code.upper() if applied_promo else None,
    )

    new_id = create_document("order", order_data)
    doc = db["order"].find_one({"_id": ObjectId(new_id)})
    d = serialize_doc(doc)
    return OrderResponse(
        id=d["id"],
        player=d["player"],
        items=[OrderItemResponse(**i) for i in d.get("items", [])],
        amount=d["amount"],
        currency=d.get("currency", "RUB"),
        status=d["status"],
        email=d.get("email"),
        server=d.get("server"),
        promo_code=d.get("promo_code"),
    )

@app.post("/api/orders/{order_id}/pay", response_model=OrderResponse)
def simulate_pay(order_id: str):
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
    d = serialize_doc(res)
    return OrderResponse(
        id=d["id"],
        player=d["player"],
        items=[OrderItemResponse(**i) for i in d.get("items", [])],
        amount=d["amount"],
        currency=d.get("currency", "RUB"),
        status=d["status"],
        email=d.get("email"),
        server=d.get("server"),
        promo_code=d.get("promo_code"),
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
