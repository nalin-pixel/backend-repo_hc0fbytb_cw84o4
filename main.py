import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Listing

# Optional heavy deps are imported lazily in functions

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

# --------- Helper AI-ish utilities ---------

def ai_quality(listing: Dict[str, Any]) -> Dict[str, Any]:
    score = 0
    tips: List[str] = []
    title = (listing.get("title") or "").strip()
    desc = (listing.get("description") or "").strip()
    images = listing.get("images") or []
    price = listing.get("price")
    city = listing.get("city")

    if len(title) >= 20:
        score += 15
    else:
        tips.append("Doplň dlhší a informatívnejší názov (aspoň 20 znakov).")

    if len(desc) >= 120:
        score += 25
    elif len(desc) >= 60:
        score += 15
        tips.append("Skús pridať podrobnejší popis (viac ako 120 znakov).")
    else:
        tips.append("Popis je veľmi krátky – pridaj parametre, stav, záruku, miesto odberu.")

    if images and len(images) >= 3:
        score += 25
    elif images:
        score += 15
        tips.append("Pridaj viac fotiek (aspoň 3) pre vyššiu dôveryhodnosť.")
    else:
        tips.append("Pridaj aspoň jednu kvalitnú fotku.")

    if isinstance(price, (int, float)) and price > 0:
        score += 15
    else:
        tips.append("Uveď realistickú cenu.")

    if city:
        score += 10
    else:
        tips.append("Uveď mesto / lokalitu pre lepšie filtrovanie.")

    score = min(100, score + 10)  # base trust boost
    return {"quality_score": score, "quality_feedback": tips}

CATEGORY_MAP = {
    "byt": "Reality",
    "dom": "Reality",
    "realita": "Reality",
    "auto": "Auto",
    "iphone": "Elektronika",
    "telef": "Elektronika",
    "počíta": "Elektronika",
    "bike": "Šport",
    "bicy": "Šport",
}

CITY_RE = re.compile(r"(bratislava|košice|presov|prešov|žilina|nitra|trnava|banská bystrica|banska bystrica)", re.I)
PRICE_RE = re.compile(r"(do|under|max)\s*(\d+[\s\.,]?\d*)|\b(\d+[\s\.,]?\d*)\s*(eur|€)\b", re.I)


def parse_chat_query(text: str) -> Dict[str, Any]:
    t = text.lower()
    filters: Dict[str, Any] = {}

    # price
    m = PRICE_RE.search(t)
    if m:
        num = m.group(2) or m.group(3)
        if num:
            num = float(num.replace(" ", "").replace(",", "."))
            filters["price_max"] = num

    # category
    for key, cat in CATEGORY_MAP.items():
        if key in t:
            filters["category"] = cat
            break

    # city
    cm = CITY_RE.search(t)
    if cm:
        city = cm.group(1)
        city = city.title().replace("Banska", "Banská").replace("Bystrica", "Bystrica")
        filters["city"] = city

    # free text
    filters["q"] = t
    return filters

# -------- Listings API --------
class ListingCreate(Listing):
    pass

@app.post("/api/listings", response_model=dict)
def create_listing(payload: ListingCreate):
    try:
        data = payload.model_dump()
        # AI quality
        quality = ai_quality(data)
        data.update(quality)
        # compute image hashes if URLs provided
        if data.get("images"):
            hashes = []
            try:
                from PIL import Image
                import imagehash
                for url in data["images"]:
                    try:
                        r = requests.get(url, timeout=6)
                        r.raise_for_status()
                        from io import BytesIO
                        img = Image.open(BytesIO(r.content)).convert('RGB')
                        ph = imagehash.phash(img)
                        hashes.append(str(ph))
                    except Exception:
                        continue
            except Exception:
                pass
            if hashes:
                data["images_hashes"] = hashes
        _id = db["listing"].insert_one({**data, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}).inserted_id
        return {"id": str(_id), **quality}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/listings", response_model=List[dict])
def list_listings(
    q: Optional[str] = Query(None, description="Full-text search in title/description"),
    category: Optional[str] = None,
    city: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    seller_email: Optional[str] = None,
    featured_only: Optional[bool] = False,
    limit: int = 24,
):
    try:
        filter_dict: dict = {}
        if category:
            filter_dict["category"] = {"$regex": f"^{category}$", "$options": "i"}
        if city:
            filter_dict["city"] = {"$regex": city, "$options": "i"}
        if seller_email:
            filter_dict["seller_email"] = seller_email
        if featured_only:
            filter_dict["featured"] = True
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
            quality = ai_quality(d)
            d.update(quality)
            create_document("listing", d)
            inserted += 1
        return {"inserted": inserted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------- AI chat search --------
@app.post("/api/ai/chat-search")
def ai_chat_search(payload: Dict[str, Any]):
    try:
        message = payload.get("message") or ""
        limit = int(payload.get("limit") or 12)
        if not message:
            return {"message": "", "filters": {}, "results": []}
        filters = parse_chat_query(message)
        results = list_listings(
            q=filters.get("q"),
            category=filters.get("category"),
            city=filters.get("city"),
            price_min=None,
            price_max=filters.get("price_max"),
            limit=limit,
        )
        reply_parts = ["Našiel som výsledky podľa tvojej požiadavky."]
        if filters.get("category"):
            reply_parts.append(f"Kategória: {filters['category']}")
        if filters.get("city"):
            reply_parts.append(f"Mesto: {filters['city']}")
        if filters.get("price_max"):
            reply_parts.append(f"Cena do: {int(filters['price_max'])} €")
        return {"message": " | ".join(reply_parts), "filters": filters, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------- Image search --------
@app.post("/api/ai/image-search")
def ai_image_search(payload: Dict[str, Any]):
    try:
        image_url = payload.get("image_url")
        limit = int(payload.get("limit") or 12)
        if not image_url:
            raise HTTPException(status_code=400, detail="image_url required")
        # compute hash
        try:
            from PIL import Image
            import imagehash
            r = requests.get(image_url, timeout=6)
            r.raise_for_status()
            from io import BytesIO
            img = Image.open(BytesIO(r.content)).convert('RGB')
            target_hash = imagehash.phash(img)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Unable to process image: {e}")
        # scan listings
        candidates = db["listing"].find({"images_hashes": {"$exists": True, "$ne": []}}).limit(200)
        scored = []
        for d in candidates:
            for h in d.get("images_hashes", []):
                try:
                    from imagehash import ImageHash
                    dist = target_hash - ImageHash.from_hex(h) if hasattr(ImageHash, 'from_hex') else target_hash - imagehash.ImageHash.from_hex(h)
                except Exception:
                    # fallback simple hamming between hex strings
                    dist = sum(a != b for a, b in zip(str(target_hash), h))
                scored.append((dist, d))
                break
        scored.sort(key=lambda x: x[0])
        out = []
        for dist, d in scored[:limit]:
            d["id"] = str(d.pop("_id"))
            d["similarity"] = max(0, 100 - dist * 5)
            out.append(d)
        return {"results": out}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------- Users, coins, feature (topovanie) --------
@app.post("/api/users/upsert")
def upsert_user(payload: Dict[str, Any]):
    try:
        email = payload.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="email required")
        existing = db["user"].find_one({"email": email})
        base = {
            "email": email,
            "name": payload.get("name"),
            "phone": payload.get("phone"),
            "bio": payload.get("bio"),
            "avatar": payload.get("avatar"),
            "coins": int(payload.get("coins") or (existing.get("coins") if existing else 0)),
            "admin": bool(payload.get("admin") or (existing.get("admin") if existing else False)),
            "updated_at": datetime.now(timezone.utc)
        }
        if existing:
            db["user"].update_one({"_id": existing["_id"]}, {"$set": base})
            existing.update(base)
            existing["id"] = str(existing.pop("_id"))
            return existing
        else:
            base["created_at"] = datetime.now(timezone.utc)
            _id = db["user"].insert_one(base).inserted_id
            base["id"] = str(_id)
            return base
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/me")
def get_me(email: str):
    try:
        u = db["user"].find_one({"email": email})
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        u["id"] = str(u.pop("_id"))
        return u
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/coins/purchase")
def purchase_coins(payload: Dict[str, Any]):
    try:
        email = payload.get("email")
        amount = int(payload.get("amount") or 0)
        if not email or amount <= 0:
            raise HTTPException(status_code=400, detail="email and positive amount required")
        u = db["user"].find_one({"email": email})
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        db["user"].update_one({"_id": u["_id"]}, {"$inc": {"coins": amount}})
        db["coin_transaction"].insert_one({
            "email": email,
            "amount": amount,
            "type": "purchase",
            "created_at": datetime.now(timezone.utc)
        })
        u = db["user"].find_one({"_id": u["_id"]})
        u["id"] = str(u.pop("_id"))
        return u
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/listings/{listing_id}/feature")
def feature_listing(listing_id: str, payload: Dict[str, Any]):
    try:
        email = payload.get("email")
        days = int(payload.get("days") or 7)
        cost = int(payload.get("cost") or (days * 10))
        if not email:
            raise HTTPException(status_code=400, detail="email required")
        if not ObjectId.is_valid(listing_id):
            raise HTTPException(status_code=400, detail="Invalid ID")
        u = db["user"].find_one({"email": email})
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        if (u.get("coins") or 0) < cost:
            raise HTTPException(status_code=400, detail="Nedostatok mincí")
        db["user"].update_one({"_id": u["_id"]}, {"$inc": {"coins": -cost}})
        until = datetime.now(timezone.utc) + timedelta(days=days)
        db["listing"].update_one({"_id": ObjectId(listing_id)}, {"$set": {"featured": True, "featured_until": until}})
        db["coin_transaction"].insert_one({
            "email": email,
            "listing_id": listing_id,
            "amount": -cost,
            "type": "feature",
            "days": days,
            "created_at": datetime.now(timezone.utc)
        })
        doc = db["listing"].find_one({"_id": ObjectId(listing_id)})
        doc["id"] = str(doc.pop("_id"))
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------- Admin --------
@app.get("/api/admin/overview")
def admin_overview(email: str):
    try:
        admin = db["user"].find_one({"email": email, "admin": True})
        if not admin:
            raise HTTPException(status_code=403, detail="Forbidden")
        total_users = db["user"].count_documents({})
        total_listings = db["listing"].count_documents({})
        featured_active = db["listing"].count_documents({"featured": True})
        revenue = sum(t.get("amount", 0) for t in db["coin_transaction"].find({"type": "purchase"}))
        return {
            "total_users": total_users,
            "total_listings": total_listings,
            "featured_active": featured_active,
            "revenue": revenue,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
