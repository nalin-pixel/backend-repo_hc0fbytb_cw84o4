import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Listing

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

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
            response["database_name"] = db.name if hasattr(db, 'name') else "❌ Not Set"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response

# -------- Listings API --------
class ListingCreate(Listing):
    pass

@app.post("/api/listings", response_model=dict)
def create_listing(payload: ListingCreate):
    try:
        _id = create_document("listing", payload)
        return {"id": _id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/listings", response_model=List[dict])
def list_listings(
    q: Optional[str] = Query(None, description="Full-text search in title/description"),
    category: Optional[str] = None,
    city: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    limit: int = 24,
):
    try:
        filter_dict: dict = {}
        if category:
            filter_dict["category"] = {"$regex": f"^{category}$", "$options": "i"}
        if city:
            filter_dict["city"] = {"$regex": city, "$options": "i"}
        if price_min is not None or price_max is not None:
            rng = {}
            if price_min is not None:
                rng["$gte"] = price_min
            if price_max is not None:
                rng["$lte"] = price_max
            filter_dict["price"] = rng
        if q:
            filter_dict["$or"] = [
                {"title": {"$regex": q, "$options": "i"}},
                {"description": {"$regex": q, "$options": "i"}},
            ]

        docs = get_documents("listing", filter_dict, limit)
        out = []
        for d in docs:
            d["id"] = str(d.get("_id"))
            d.pop("_id", None)
            out.append(d)
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/listings/{listing_id}", response_model=dict)
def get_listing(listing_id: str):
    try:
        if not ObjectId.is_valid(listing_id):
            raise HTTPException(status_code=400, detail="Invalid ID")
        doc = db["listing"].find_one({"_id": ObjectId(listing_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        doc["id"] = str(doc.pop("_id"))
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/seed-demo", response_model=dict)
def seed_demo():
    try:
        demo = [
            {
                "title": "iPhone 14 Pro 256GB",
                "description": "Top stav, krabica, záruka. Vymenená batéria.",
                "price": 899.0,
                "category": "Elektronika",
                "city": "Bratislava",
                "latitude": 48.1486,
                "longitude": 17.1077,
                "images": [],
                "seller_name": "Marek",
                "currency": "EUR",
                "featured": True,
            },
            {
                "title": "Trek FX 3 Disc",
                "description": "Mestský bicykel, pravidelne servisovaný.",
                "price": 420.0,
                "category": "Šport",
                "city": "Žilina",
                "latitude": 49.2231,
                "longitude": 18.7394,
                "images": [],
                "seller_name": "Zuzana",
                "currency": "EUR",
                "featured": False,
            },
            {
                "title": "Prenájom 2i bytu v centre",
                "description": "Kompletne zariadený, 60 m², lodžia.",
                "price": 850.0,
                "category": "Reality",
                "city": "Košice",
                "latitude": 48.7164,
                "longitude": 21.2611,
                "images": [],
                "seller_name": "Peter",
                "currency": "EUR",
                "featured": False,
            },
        ]
        inserted = 0
        for d in demo:
            create_document("listing", d)
            inserted += 1
        return {"inserted": inserted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
