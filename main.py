import os
import csv
import io
import math
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Tuple

from database import create_document, get_documents
from schemas import Review

OURAIRPORTS_CSV_URL = "https://ourairports.com/data/airports.csv"

app = FastAPI(title="Routes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Airport data source (OurAirports) ---
AIRPORTS: Dict[str, Dict] = {}


def load_airports_from_ourairports(max_airports: Optional[int] = None) -> Dict[str, Dict]:
    """Download and parse airports from OurAirports CSV.
    Keep only large/medium airports with valid IATA and coordinates.
    If max_airports is provided, cap the number; otherwise include all.
    """
    try:
        resp = requests.get(OURAIRPORTS_CSV_URL, timeout=20)
        resp.raise_for_status()
        data = resp.content.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(data))
        airports: Dict[str, Dict] = {}
        for row in reader:
            iata = (row.get("iata_code") or "").strip().upper()
            if not iata or len(iata) != 3 or iata == "\\N":
                continue
            t = (row.get("type") or "").strip()
            if t not in {"large_airport", "medium_airport"}:
                continue
            name = (row.get("name") or "").strip()
            lat = row.get("latitude_deg")
            lon = row.get("longitude_deg")
            iso_country = (row.get("iso_country") or "").strip()
            municipality = (row.get("municipality") or "").strip()
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                continue
            airports[iata] = {
                "name": name,
                "city": municipality or name,
                "country": iso_country,
                "lat": lat_f,
                "lng": lon_f,
            }
            if max_airports is not None and len(airports) >= max_airports:
                break
        return airports
    except Exception:
        return {}


# Fallback minimal curated set if OurAirports isn't reachable
FALLBACK_AIRPORTS = {
    "JFK": {"name": "John F. Kennedy International", "city": "New York", "country": "US", "lat": 40.6413, "lng": -73.7781},
    "LHR": {"name": "London Heathrow", "city": "London", "country": "GB", "lat": 51.4700, "lng": -0.4543},
    "CDG": {"name": "Paris Charles de Gaulle", "city": "Paris", "country": "FR", "lat": 49.0097, "lng": 2.5479},
    "DXB": {"name": "Dubai International", "city": "Dubai", "country": "AE", "lat": 25.2532, "lng": 55.3657},
}

# Simple static graph of direct routes (demo only)
ROUTES = {
    "JFK": ["LHR", "CDG", "DXB"],
    "LHR": ["JFK", "CDG", "DXB"],
    "CDG": ["JFK", "LHR", "DXB"],
    "DXB": ["JFK", "LHR", "CDG"],
}


class ReviewIn(BaseModel):
    airport_iata: str
    name: str
    rating: int
    comment: Optional[str] = None


def ensure_airports_loaded():
    global AIRPORTS
    if AIRPORTS:
        return
    # Load all available medium/large airports to ensure global coverage
    loaded = load_airports_from_ourairports(max_airports=None)
    if loaded:
        AIRPORTS = loaded
    else:
        AIRPORTS = FALLBACK_AIRPORTS


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def nearest_connections(iata: str, k: int = 8, max_distance_km: Optional[float] = None) -> List[str]:
    """Return up to k nearest airports by great-circle distance.
    Optionally filter by a maximum distance.
    """
    if iata not in AIRPORTS:
        return []
    src = AIRPORTS[iata]
    src_coord = (src["lat"], src["lng"])
    distances: List[Tuple[float, str]] = []
    for code, info in AIRPORTS.items():
        if code == iata:
            continue
        d = haversine_km(src_coord, (info["lat"], info["lng"]))
        if max_distance_km is None or d <= max_distance_km:
            distances.append((d, code))
    distances.sort(key=lambda x: x[0])
    return [code for _, code in distances[:k]]


@app.get("/")
def root():
    return {"status": "ok", "message": "Routes API running"}


@app.get("/airports")
def list_airports():
    ensure_airports_loaded()
    # Return a stable list sorted by IATA for consistency
    return [{"iata": code, **AIRPORTS[code]} for code in sorted(AIRPORTS.keys())]


@app.get("/routes/{iata}")
def get_routes(iata: str):
    ensure_airports_loaded()
    iata = iata.upper()
    if iata not in AIRPORTS:
        raise HTTPException(status_code=404, detail="Airport not found")
    # Prefer static demo routes when present; otherwise compute nearest neighbors as a sensible default
    route_codes = [c for c in ROUTES.get(iata, []) if c in AIRPORTS]
    if not route_codes:
        route_codes = nearest_connections(iata, k=8)
    connections = [{"iata": c, **AIRPORTS[c]} for c in route_codes]
    return {
        "airport": {"iata": iata, **AIRPORTS[iata]},
        "connections": connections,
    }


@app.get("/destination/{iata}")
def destination_summary(iata: str):
    ensure_airports_loaded()
    iata = iata.upper()
    if iata not in AIRPORTS:
        raise HTTPException(status_code=404, detail="Airport not found")
    city = AIRPORTS[iata]["city"]
    wiki = f"https://en.wikipedia.org/wiki/{city.replace(' ', '_')}"
    search_flights = f"https://www.google.com/travel/flights?q=Flights%20to%20{iata}"
    search_hotels = f"https://www.google.com/travel/hotels/{city.replace(' ', '%20')}"
    return {
        "airport": {"iata": iata, **AIRPORTS[iata]},
        "links": {
            "flights": search_flights,
            "hotels": search_hotels,
            "wikipedia": wiki,
        },
    }


@app.post("/reviews", status_code=201)
def add_review(review: ReviewIn):
    r = Review(**review.model_dump())
    inserted_id = create_document("review", r)
    return {"id": inserted_id}


@app.get("/reviews/{iata}")
def list_reviews(iata: str, limit: int = 50):
    items = get_documents("review", {"airport_iata": iata.upper()}, limit)
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
