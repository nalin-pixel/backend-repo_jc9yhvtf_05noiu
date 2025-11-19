import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from database import create_document, get_documents
from schemas import Review

app = FastAPI(title="Routes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static data for airports and direct routes ---
# Minimal curated set of major international airports and their direct connections (IATA codes)
# In a real-world app you'd populate this from an aviation dataset.
AIRPORTS = {
    "JFK": {"name": "New York JFK", "city": "New York", "country": "USA", "lat": 40.6413, "lng": -73.7781},
    "LHR": {"name": "London Heathrow", "city": "London", "country": "UK", "lat": 51.4700, "lng": -0.4543},
    "CDG": {"name": "Paris Charles de Gaulle", "city": "Paris", "country": "France", "lat": 49.0097, "lng": 2.5479},
    "DXB": {"name": "Dubai International", "city": "Dubai", "country": "UAE", "lat": 25.2532, "lng": 55.3657},
    "HND": {"name": "Tokyo Haneda", "city": "Tokyo", "country": "Japan", "lat": 35.5494, "lng": 139.7798},
    "SIN": {"name": "Singapore Changi", "city": "Singapore", "country": "Singapore", "lat": 1.3644, "lng": 103.9915},
    "SYD": {"name": "Sydney", "city": "Sydney", "country": "Australia", "lat": -33.9399, "lng": 151.1753},
    "FRA": {"name": "Frankfurt", "city": "Frankfurt", "country": "Germany", "lat": 50.0379, "lng": 8.5622},
    "IST": {"name": "Istanbul", "city": "Istanbul", "country": "Turkey", "lat": 41.2753, "lng": 28.7519},
    "GRU": {"name": "São Paulo Guarulhos", "city": "São Paulo", "country": "Brazil", "lat": -23.4356, "lng": -46.4731},
}

# Simple graph of direct routes
ROUTES = {
    "JFK": ["LHR", "CDG", "DXB", "HND", "FRA"],
    "LHR": ["JFK", "CDG", "DXB", "SIN", "IST"],
    "CDG": ["JFK", "LHR", "DXB", "FRA"],
    "DXB": ["JFK", "LHR", "CDG", "HND", "SIN", "SYD"],
    "HND": ["JFK", "DXB", "SIN"],
    "SIN": ["LHR", "DXB", "HND", "SYD"],
    "SYD": ["DXB", "SIN"],
    "FRA": ["JFK", "CDG", "IST"],
    "IST": ["LHR", "FRA", "GRU"],
    "GRU": ["IST"]
}

class ReviewIn(BaseModel):
    airport_iata: str
    name: str
    rating: int
    comment: Optional[str] = None

@app.get("/")
def root():
    return {"status": "ok", "message": "Routes API running"}

@app.get("/airports")
def list_airports():
    return [{"iata": code, **data} for code, data in AIRPORTS.items()]

@app.get("/routes/{iata}")
def get_routes(iata: str):
    iata = iata.upper()
    if iata not in AIRPORTS:
        raise HTTPException(status_code=404, detail="Airport not found")
    connections = ROUTES.get(iata, [])
    return {
        "airport": {"iata": iata, **AIRPORTS[iata]},
        "connections": [{"iata": c, **AIRPORTS[c]} for c in connections if c in AIRPORTS]
    }

@app.get("/destination/{iata}")
def destination_summary(iata: str):
    iata = iata.upper()
    if iata not in AIRPORTS:
        raise HTTPException(status_code=404, detail="Airport not found")
    city = AIRPORTS[iata]["city"]
    wiki = f"https://en.wikipedia.org/wiki/{city.replace(' ', '_')}"
    # provide external links placeholders
    search_flights = f"https://www.google.com/travel/flights?q=Flights%20to%20{iata}"
    search_hotels = f"https://www.google.com/travel/hotels/{city.replace(' ', '%20')}"
    return {
        "airport": {"iata": iata, **AIRPORTS[iata]},
        "links": {
            "flights": search_flights,
            "hotels": search_hotels,
            "wikipedia": wiki
        }
    }

@app.post("/reviews", status_code=201)
def add_review(review: ReviewIn):
    r = Review(**review.model_dump())
    inserted_id = create_document("review", r)
    return {"id": inserted_id}

@app.get("/reviews/{iata}")
def list_reviews(iata: str, limit: int = 50):
    items = get_documents("review", {"airport_iata": iata.upper()}, limit)
    # Convert ObjectId and datetime to strings for JSON compatibility
    def serialize(doc):
        doc["_id"] = str(doc.get("_id"))
        if "created_at" in doc:
            doc["created_at"] = str(doc["created_at"])  
        if "updated_at" in doc:
            doc["updated_at"] = str(doc["updated_at"])  
        return doc
    return [serialize(d) for d in items]

@app.get("/test")
def test_database():
    """Quick status for backend and DB"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
    }
    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Connected"
    except Exception:
        pass
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
