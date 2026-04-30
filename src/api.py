"""
FastAPI Backend for Eco-Arbitrage
Replaces Streamlit with REST API serving agent.py logic
"""

import os
import json
import random
import time
import html as _html
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from pydantic import BaseModel

# Import the AI agent
import agent
import scraper

process_item = agent.process_item
scrape = scraper.scrape


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_data()
    yield


app = FastAPI(
    title="Eco-Arbitrage API",
    description="AI-Powered Inventory Recovery & Liquidation Engine",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_df = None
_default_csv_path = os.path.join(os.path.dirname(__file__), "data.csv")
_deployed_items: List[Dict[str, Any]] = []


def load_data(csv_path: Optional[str] = None) -> pd.DataFrame:
    global _df
    path = csv_path or _default_csv_path
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Data file not found: {path}")
    _df = pd.read_csv(path)
    return _df


def get_dataframe() -> pd.DataFrame:
    global _df
    if _df is None:
        return load_data()
    return _df


# ── Pydantic model for /deploy ──────────────────────────────────────────────
class DeployRequest(BaseModel):
    sku: str
    product_name: str
    resale_price: float
    platform: str           # "ebay" | "depop" | "local"
    # optional enrichment fields (used by listing page)
    category: Optional[str] = None
    age_days: Optional[int] = None
    co2_kg: Optional[float] = None
    strategy: Optional[str] = None
    urgency: Optional[str] = None
    est_profit: Optional[float] = None


# ============ CORE ENDPOINTS ============

@app.get("/")
def root():
    return {
        "name": "Eco-Arbitrage API",
        "version": "1.0.0",
        "status": "ACTIVE",
        "endpoints": {
            "GET /": "API info",
            "GET /inventory": "Get filtered inventory",
            "POST /optimize": "Run AI optimization (streaming)",
            "GET /stats": "Get KPI summary",
            "POST /upload": "Upload CSV file",
            "GET /categories": "Get unique categories",
            "POST /deploy": "Deploy an item to a marketplace",
            "GET /deployments": "Retrieve all deployed listings",
            "GET /listing/{listing_id}": "View a live listing page",
        }
    }


@app.get("/inventory")
def get_inventory(
    min_age: int = Query(0, ge=0),
    max_age: int = Query(500, ge=0),
    categories: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    df = get_dataframe()
    filtered = df[(df["inventory_age_days"] >= min_age) & (df["inventory_age_days"] <= max_age)]
    if categories:
        filtered = filtered[filtered["category"].isin([c.strip() for c in categories.split(",")])]
    if search:
        filtered = filtered[filtered["product_name"].str.contains(search, case=False, na=False)]
    result = filtered.to_dict(orient="records")
    return {"success": True, "count": len(result), "data": result}


@app.get("/categories")
def get_categories():
    df = get_dataframe()
    return {"success": True, "categories": sorted(df["category"].unique().tolist())}


@app.get("/ui")
def serve_frontend():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


@app.get("/stats")
def get_stats(min_age: int = Query(90, ge=0)):
    df = get_dataframe()
    overstock = df[df["inventory_age_days"] >= min_age]
    return {
        "success": True,
        "stats": {
            "total_inventory": len(df),
            "overstock_items": len(overstock),
            "total_value": round(df["original_cost_usd"].sum(), 2),
            "total_waste_footprint_kg": round(df["waste_footprint_kg"].sum(), 2),
            "overstock_value": round(overstock["original_cost_usd"].sum(), 2),
            "overstock_waste_kg": round(overstock["waste_footprint_kg"].sum(), 2),
            "category_breakdown": df["category"].value_counts().to_dict(),
            "at_risk_items": len(df[df["inventory_age_days"] >= 120]),
            "critical_items": len(df[df["inventory_age_days"] >= 180])
        }
    }


class OptimizerIterator:
    def __init__(self, items):
        self.items = items
        self.index = 0
        self.results = []

    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= len(self.items):
            raise StopIteration
        item = self.items[self.index]
        self.index += 1
        ai_result = process_item(item)
        profit = ai_result["resale_price"] - item["original_cost_usd"]
        result = {
            "sku": item["product_id"],
            "item": item["product_name"],
            "category": item["category"],
            "age_days": item["inventory_age_days"],
            "urgency": ai_result["urgency"],
            "resale_price": round(ai_result["resale_price"], 2),
            "est_profit": round(profit, 2),
            "co2_impact_kg": item["waste_footprint_kg"],
            "strategy": ai_result["description"],
            "progress": self.index,
            "total": len(self.items)
        }
        self.results.append(result)
        return f"data: {json.dumps(result)}\n\n"

    def get_final_results(self):
        return self.results


@app.post("/optimize")
async def run_optimization(
    min_age: int = Query(90, ge=0),
    categories: Optional[str] = Query(None)
):
    df = get_dataframe()
    filtered = df[df["inventory_age_days"] >= min_age]
    if categories:
        filtered = filtered[filtered["category"].isin([c.strip() for c in categories.split(",")])]
    if len(filtered) == 0:
        raise HTTPException(status_code=400, detail="No items match the current filters")

    items = filtered.to_dict(orient="records")

    async def generate():
        iterator = OptimizerIterator(items)
        try:
            for line in iterator:
                yield line
                await asyncio.sleep(0.1)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        results = iterator.get_final_results()
        yield f"data: {json.dumps({'done': True, 'total_processed': len(results), 'total_profit': round(sum(r['est_profit'] for r in results), 2), 'total_co2_kg': round(sum(r['co2_impact_kg'] for r in results), 2), 'high_urgency': len([r for r in results if r['urgency'] == 'high']), 'medium_urgency': len([r for r in results if r['urgency'] == 'medium']), 'low_urgency': len([r for r in results if r['urgency'] == 'low'])})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@app.post("/optimize-single")
def optimize_single_item(item: Dict[str, Any]):
    try:
        result = process_item(item)
        result["success"] = True
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape")
async def scrape_and_load(
    source: str = Query(...),
    keyword: str = Query(...),
    pages: int = Query(2, ge=1, le=5)
):
    global _df, _default_csv_path
    try:
        df = scrape(source, keyword, pages)
        if df.empty:
            raise HTTPException(status_code=400, detail="No results found.")
        output_path = os.path.join(os.path.dirname(__file__), "data.csv")
        df.to_csv(output_path, index=False)
        _df = df
        _default_csv_path = output_path
        return {"success": True, "source": source, "keyword": keyword, "row_count": len(df)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    global _df, _default_csv_path
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")
    upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(upload_dir, f"inventory_{timestamp}.csv")
    content = await file.read()
    with open(file_path, 'wb') as f:
        f.write(content)
    try:
        df = pd.read_csv(file_path)
        required = ['product_id', 'product_name', 'category', 'inventory_age_days', 'original_cost_usd', 'waste_footprint_kg']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")
        _df = df
        _default_csv_path = file_path
        return {"success": True, "message": "CSV uploaded successfully", "filename": file.filename, "row_count": len(df), "categories": df["category"].unique().tolist()}
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing CSV: {str(e)}")


@app.post("/reset")
def reset_to_default():
    global _df, _default_csv_path
    _default_csv_path = os.path.join(os.path.dirname(__file__), "data.csv")
    _df = pd.read_csv(_default_csv_path)
    return {"success": True, "message": "Reset to default dataset", "row_count": len(_df)}


# ══════════════════════════════════════════════════════════════════════════════
# DEPLOY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/deploy")
def deploy_item(req: DeployRequest):
    platform = req.platform.lower()
    if platform not in ("ebay", "depop", "local"):
        raise HTTPException(status_code=400, detail="Platform must be: ebay, depop, or local")

    rand_suffix   = random.randint(100000, 999999)
    sku_alpha     = "".join(c for c in req.sku if c.isalnum()).upper()
    now_iso       = datetime.utcnow().isoformat() + "Z"

    if platform == "ebay":
        listing_id    = f"{sku_alpha}{rand_suffix}"
        platform_fee  = round(req.resale_price * 0.1325, 2)
        net_proceeds  = round(req.resale_price - platform_fee, 2)
        extra = {
            "listing_format": "FixedPrice",
            "listing_duration": "GTC",
            "listing_title": f"{req.product_name[:80]} | Eco-Arbitrage Liquidation",
            "seller_fees_usd": platform_fee,
        }
        message = "Listed on eBay Marketplace — Good 'Til Cancelled (GTC)"

    elif platform == "depop":
        listing_id   = f"eco-{req.sku.lower()[:12]}-{rand_suffix}"
        platform_fee = round(req.resale_price * 0.10 + req.resale_price * 0.029 + 0.30, 2)
        net_proceeds = round(req.resale_price - platform_fee, 2)
        extra = {
            "listing_format": "BuyNow",
            "brand": "Eco-Arbitrage",
            "condition": "Good",
            "boost_eligible": True,
        }
        message = "Simulated Depop listing — 10% seller fee + payment processing"

    else:  # local
        listing_id   = f"LB-{sku_alpha}-{rand_suffix}"
        platform_fee = 0.0
        net_proceeds = req.resale_price
        extra = {
            "board": "EcoArbitrage Local Marketplace",
            "visibility": "Internal",
            "auto_expires_days": 30,
        }
        message = "Posted to Local Marketplace Board — no fees, 30-day listing"

    # ── Listing URL now points to the local listing page ─────────────────────
    listing_url = f"http://localhost:8000/listing/{listing_id}"

    entry: Dict[str, Any] = {
        "success": True,
        "platform": platform,
        "sku": req.sku,
        "product_name": req.product_name,
        "listing_id": listing_id,
        "listing_url": listing_url,
        "resale_price": req.resale_price,
        "platform_fee_usd": platform_fee,
        "net_proceeds_usd": net_proceeds,
        "message": message,
        "deployed_at": now_iso,
        "status": "active",
        # enrichment from frontend
        "category": req.category or "General",
        "age_days": req.age_days or 0,
        "co2_kg": req.co2_kg or 0,
        "strategy": req.strategy or "",
        "urgency": req.urgency or "medium",
        "est_profit": req.est_profit or 0,
        **extra,
    }

    _deployed_items.append(entry)
    return entry


@app.get("/deployments")
def get_deployments():
    return {
        "success": True,
        "count": len(_deployed_items),
        "total_revenue": round(sum(d["net_proceeds_usd"] for d in _deployed_items), 2),
        "deployments": _deployed_items,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LISTING PAGE  —  GET /listing/{listing_id}
# Each platform gets a fully styled, realistic-looking HTML listing page.
# ══════════════════════════════════════════════════════════════════════════════

def _category_emoji(cat: str) -> str:
    cat = (cat or "").lower()
    for k, v in {
        "electron": "💻", "comput": "💻", "phone": "📱", "tablet": "📱",
        "cloth": "👗", "apparel": "👔", "fashion": "👗", "wear": "👕",
        "furnitur": "🛋", "home": "🏠", "decor": "🖼", "bed": "🛏",
        "book": "📚", "media": "📀", "music": "🎵",
        "toy": "🧸", "game": "🎮", "kid": "🧒",
        "sport": "⚽", "fitness": "🏋", "outdoor": "🏕",
        "kitchen": "🍳", "cook": "🍳", "appli": "🍽",
        "tool": "🔧", "hardware": "🔨", "auto": "🚗",
        "beauty": "💄", "health": "💊", "care": "🧴",
        "garden": "🌱", "plant": "🌿",
        "jewel": "💍", "watch": "⌚",
        "art": "🎨", "craft": "✂",
    }.items():
        if k in cat:
            return v
    return "📦"


def _ebay_html(item: dict) -> str:
    name         = _html.escape(item.get("product_name", "Product"))
    price        = float(item.get("resale_price", 0))
    category     = _html.escape(item.get("category", "General"))
    emoji        = _category_emoji(item.get("category", ""))
    listing_id   = _html.escape(item.get("listing_id", ""))
    strategy     = _html.escape(item.get("strategy", ""))
    age_days     = int(item.get("age_days", 0))
    co2_kg       = item.get("co2_kg", 0)
    net          = float(item.get("net_proceeds_usd", price))
    fee          = float(item.get("platform_fee_usd", 0))
    deployed_at  = str(item.get("deployed_at", ""))[:10]
    urgency      = item.get("urgency", "medium")
    sku          = _html.escape(item.get("sku", ""))

    condition       = "Good" if age_days > 180 else "Very Good" if age_days > 90 else "Like New"
    urgency_color   = {"high": "#c40000", "medium": "#e47911", "low": "#007600"}.get(urgency, "#e47911")
    desc            = strategy if strategy else f"Quality {category} item from the Eco-Arbitrage liquidation program. Priced for fast resale."

    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f7f7f7; color: #333; font-size: 14px; }
.ebay-header { background: white; border-bottom: 1px solid #e5e5e5; padding: 10px 24px; display: flex; align-items: center; gap: 20px; position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.ebay-logo { font-size: 38px; font-weight: 900; letter-spacing: -2px; line-height: 1; user-select: none; }
.e { color: #e53238; } .b1 { color: #0064d2; } .a { color: #f5af02; } .y { color: #86b817; }
.search-wrap { flex: 1; max-width: 580px; display: flex; height: 38px; }
.search-wrap input { flex: 1; border: 2px solid #c7c7c7; border-right: none; border-radius: 4px 0 0 4px; padding: 0 14px; font-size: 14px; outline: none; background: #fff; }
.search-wrap input:focus { border-color: #0064d2; }
.search-btn { background: #0064d2; color: white; border: none; padding: 0 22px; border-radius: 0 4px 4px 0; font-size: 16px; cursor: pointer; }
.sub-nav { background: white; border-bottom: 1px solid #e5e5e5; padding: 0 24px; display: flex; }
.sub-nav span { padding: 10px 14px; font-size: 13px; color: #333; cursor: pointer; border-bottom: 3px solid transparent; display: block; }
.sub-nav span:hover { border-bottom-color: #0064d2; color: #0064d2; }
.demo-banner { background: #fff8e1; border-bottom: 2px solid #ffc107; color: #7a6000; padding: 9px 24px; font-size: 12px; font-weight: 600; }
.breadcrumb { padding: 10px 24px; font-size: 12px; color: #767676; background: white; border-bottom: 1px solid #f0f0f0; }
.breadcrumb a { color: #0064d2; text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }
.listing-main { max-width: 1180px; margin: 20px auto; padding: 0 24px; display: grid; grid-template-columns: 460px 1fr; gap: 32px; }
.img-panel {}
.main-img { width: 100%; aspect-ratio: 1/1; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 70%, #533483 100%); border-radius: 4px; border: 1px solid #e5e5e5; display: flex; align-items: center; justify-content: center; font-size: 120px; position: relative; overflow: hidden; cursor: zoom-in; }
.main-img::after { content: 'ECO-ARBITRAGE DEMO'; position: absolute; bottom: 14px; right: 14px; background: rgba(0,0,0,0.55); color: rgba(255,255,255,0.8); font-size: 9px; font-weight: 800; padding: 4px 8px; border-radius: 3px; letter-spacing: 1px; }
.thumb-row { display: flex; gap: 8px; margin-top: 10px; }
.thumb { width: 64px; height: 64px; border: 2px solid #e5e5e5; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 26px; cursor: pointer; background: white; }
.thumb:first-child { border-color: #0064d2; }
.thumb:hover { border-color: #0064d2; }
.eco-box { margin-top: 14px; padding: 12px 14px; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 4px; }
.eco-box-title { font-size: 11px; font-weight: 700; color: #2e7d32; letter-spacing: 0.5px; margin-bottom: 4px; }
.eco-box-body { font-size: 13px; color: #333; }
.buy-box { display: flex; flex-direction: column; gap: 14px; }
.item-condition { display: inline-block; background: #ebf4ff; color: #0064d2; font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 3px; border: 1px solid #b3d4f5; text-transform: uppercase; letter-spacing: 0.5px; }
.item-title { font-size: 21px; font-weight: 400; color: #111; line-height: 1.35; }
.stars { color: #ffa500; font-size: 13px; }
.price-box { background: white; border: 1px solid #e5e5e5; border-radius: 4px; padding: 18px; }
.price-lbl { font-size: 12px; color: #767676; margin-bottom: 4px; }
.price-num { font-size: 30px; font-weight: 700; color: #111; }
.price-ship { font-size: 13px; color: #007600; font-weight: 600; margin-top: 6px; }
.price-fee { font-size: 11px; color: #767676; margin-top: 4px; }
.btn-buy-now { display: block; width: 100%; padding: 14px; background: #0064d2; color: white; border: none; border-radius: 24px; font-size: 16px; font-weight: 600; cursor: not-allowed; margin-top: 14px; opacity: 0.82; text-align: center; }
.btn-add-cart { display: block; width: 100%; padding: 14px; background: white; color: #0064d2; border: 2px solid #0064d2; border-radius: 24px; font-size: 16px; font-weight: 600; cursor: not-allowed; margin-top: 8px; text-align: center; }
.demo-note { text-align: center; font-size: 11px; color: #aaa; margin-top: 6px; }
.seller-row { border: 1px solid #e5e5e5; border-radius: 4px; padding: 14px 16px; background: white; display: flex; align-items: center; gap: 12px; }
.seller-av { width: 44px; height: 44px; background: linear-gradient(135deg, #0064d2, #00aaff); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 18px; flex-shrink: 0; }
.seller-name { font-weight: 700; color: #0064d2; font-size: 14px; }
.seller-fb { font-size: 12px; color: #767676; }
.seller-badge { font-size: 11px; color: #007600; font-weight: 700; }
.trust-list { display: flex; flex-direction: column; gap: 8px; }
.trust-item { display: flex; align-items: flex-start; gap: 10px; font-size: 12px; color: #333; }
.trust-icon { font-size: 16px; flex-shrink: 0; }
.listing-lower { max-width: 1180px; margin: 0 auto 40px; padding: 0 24px; display: grid; grid-template-columns: 1fr 340px; gap: 20px; }
.card { background: white; border: 1px solid #e5e5e5; border-radius: 4px; overflow: hidden; margin-bottom: 16px; }
.card-head { padding: 12px 16px; border-bottom: 1px solid #f0f0f0; font-weight: 700; font-size: 14px; background: #f9f9f9; }
.card-body { padding: 16px; font-size: 14px; line-height: 1.7; color: #555; }
.specs-tbl { width: 100%; border-collapse: collapse; }
.specs-tbl tr:nth-child(even) td { background: #f9f9f9; }
.specs-tbl td { padding: 9px 14px; border-bottom: 1px solid #f0f0f0; font-size: 13px; color: #555; }
.specs-tbl td:first-child { font-weight: 600; color: #333; width: 42%; }
.urgency-row td { background: #fff8e1 !important; }
.eco-tag { display: inline-flex; align-items: center; gap: 5px; background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; margin-top: 10px; }
.fin-row { display: flex; justify-content: space-between; align-items: center; padding: 7px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.fin-row:last-child { border: none; border-top: 2px solid #e5e5e5; padding-top: 10px; }
.footer { background: #333; color: #bbb; padding: 20px 24px; text-align: center; font-size: 12px; }
@media (max-width: 800px) { .listing-main, .listing-lower { grid-template-columns: 1fr; } }
"""

    body_html = f"""
<header class="ebay-header">
  <div class="ebay-logo"><span class="e">e</span><span class="b1">b</span><span class="a">a</span><span class="y">y</span></div>
  <div class="search-wrap">
    <input type="text" value="{name}" readonly />
    <button class="search-btn">🔍</button>
  </div>
</header>
<nav class="sub-nav">
  <span>Daily Deals</span><span>Brand Outlet</span><span>Help &amp; Contact</span><span>Sell</span>
</nav>
<div class="demo-banner">📋 &nbsp;Demo Listing — Generated by Eco-Arbitrage AI &nbsp;·&nbsp; Listing ID: {listing_id}</div>
<div class="breadcrumb">
  <a href="#">eBay</a> › <a href="#">{category}</a> › <a href="#">All Items</a> › {name[:50]}{'...' if len(name) > 50 else ''}
</div>

<div class="listing-main">
  <div class="img-panel">
    <div class="main-img">{emoji}</div>
    <div class="thumb-row">
      <div class="thumb">{emoji}</div>
      <div class="thumb">📦</div>
      <div class="thumb">🔍</div>
      <div class="thumb">✨</div>
    </div>
    <div class="eco-box">
      <div class="eco-box-title">🌿 ECO-ARBITRAGE IMPACT</div>
      <div class="eco-box-body">Reselling this item prevents <strong>{co2_kg} kg</strong> of CO₂ waste from landfill.</div>
    </div>
  </div>

  <div class="buy-box">
    <div><span class="item-condition">{condition}</span></div>
    <h1 class="item-title">{name}</h1>
    <div class="stars">★★★★★ <span style="color:#767676;font-size:12px">(142 sold)</span></div>
    <div class="price-box">
      <div class="price-lbl">Buy It Now</div>
      <div class="price-num">US ${price:,.2f}</div>
      <div class="price-ship">✓ Free shipping &nbsp;·&nbsp; Free returns</div>
      <div class="price-fee">Platform fee: ${fee:,.2f} (13.25%) &nbsp;·&nbsp; Your net: <strong>${net:,.2f}</strong></div>
      <button class="btn-buy-now">Buy It Now</button>
      <button class="btn-add-cart">Add to cart</button>
      <div class="demo-note">🔒 Demo listing — buttons disabled</div>
    </div>
    <div class="seller-row">
      <div class="seller-av">E</div>
      <div>
        <div class="seller-name">eco_arbitrage_store</div>
        <div class="seller-fb">⭐ 99.8% positive feedback &nbsp;·&nbsp; 3,421 ratings</div>
        <div class="seller-badge">✓ Top Rated Seller &nbsp;·&nbsp; Fast shipping</div>
      </div>
    </div>
    <div class="trust-list">
      <div class="trust-item"><span class="trust-icon">🛡</span><span><strong>eBay Money Back Guarantee</strong><br>Get the item you ordered or your money back.</span></div>
      <div class="trust-item"><span class="trust-icon">🔄</span><span>30-day returns &nbsp;·&nbsp; Buyer pays return shipping</span></div>
      <div class="trust-item"><span class="trust-icon">🚚</span><span>Ships within 1 business day from United States</span></div>
    </div>
  </div>
</div>

<div class="listing-lower">
  <div>
    <div class="card">
      <div class="card-head">About this item</div>
      <div class="card-body">
        <p>{desc}</p>
        <div class="eco-tag">🌿 Eco-Resale &nbsp; {co2_kg} kg CO₂ prevented</div>
      </div>
    </div>
    <div class="card">
      <div class="card-head">Item specifics</div>
      <div class="card-body" style="padding:0">
        <table class="specs-tbl">
          <tr><td>Condition</td><td>{condition}</td></tr>
          <tr><td>Category</td><td>{category}</td></tr>
          <tr><td>Brand</td><td>Eco-Arbitrage Liquidation</td></tr>
          <tr><td>SKU / Item #</td><td style="font-family:monospace">{sku}</td></tr>
          <tr><td>Listing ID</td><td style="font-family:monospace">{listing_id}</td></tr>
          <tr><td>Days in Inventory</td><td>{age_days} days</td></tr>
          <tr><td>CO₂ Impact</td><td>🌿 {co2_kg} kg prevented</td></tr>
          <tr><td>Listed</td><td>{deployed_at}</td></tr>
          <tr class="urgency-row"><td>Liquidation Priority</td><td><strong style="color:{urgency_color}">{urgency.upper()}</strong></td></tr>
        </table>
      </div>
    </div>
  </div>
  <div>
    <div class="card">
      <div class="card-head">Shipping</div>
      <div class="card-body" style="font-size:13px">
        <div style="margin-bottom:10px"><strong>🚚 Free Standard Shipping</strong><br><span style="color:#767676">Est. 3–5 business days</span></div>
        <div style="margin-bottom:10px"><strong>📦 Handling:</strong> 1 business day</div>
        <div><strong>📍 Ships from:</strong> United States</div>
      </div>
    </div>
    <div class="card">
      <div class="card-head">Returns</div>
      <div class="card-body" style="font-size:13px">
        <div style="margin-bottom:8px">✅ <strong>30-day returns</strong></div>
        <div style="color:#767676">Buyer pays return shipping.</div>
      </div>
    </div>
    <div class="card">
      <div class="card-head">Eco-Arbitrage Financials</div>
      <div class="card-body" style="padding:12px 16px">
        <div class="fin-row"><span>Listed price</span><strong>${price:,.2f}</strong></div>
        <div class="fin-row" style="color:#767676"><span>eBay FVF (13.25%)</span><span>−${fee:,.2f}</span></div>
        <div class="fin-row"><span><strong>Net proceeds</strong></span><strong style="color:#007600">${net:,.2f}</strong></div>
      </div>
    </div>
  </div>
</div>

<footer class="footer">
  Copyright © 2025 Eco-Arbitrage AI &nbsp;·&nbsp; Demo eBay Listing &nbsp;·&nbsp; Listing ID: {listing_id}
</footer>"""

    return f"<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{name} | eBay</title><style>{css}</style></head><body>{body_html}</body></html>"


def _depop_html(item: dict) -> str:
    name        = _html.escape(item.get("product_name", "Product"))
    price       = float(item.get("resale_price", 0))
    category    = _html.escape(item.get("category", "General"))
    emoji       = _category_emoji(item.get("category", ""))
    listing_id  = _html.escape(item.get("listing_id", ""))
    strategy    = _html.escape(item.get("strategy", ""))
    age_days    = int(item.get("age_days", 0))
    co2_kg      = item.get("co2_kg", 0)
    net         = float(item.get("net_proceeds_usd", price))
    fee         = float(item.get("platform_fee_usd", 0))
    deployed_at = str(item.get("deployed_at", ""))[:10]
    sku         = _html.escape(item.get("sku", ""))

    condition = "Good" if age_days > 180 else "Great" if age_days > 90 else "Like New"
    desc      = strategy if strategy else f"Excellent {category} item from a trusted Eco-Arbitrage seller. Great condition, fast dispatch."
    tags_html = "".join(
        f'<span style="padding:5px 12px;background:#f5f5f5;border-radius:100px;font-size:12px;color:#555;cursor:pointer">#{t}</span>'
        for t in [category.lower().replace(" ", ""), "ecoresale", "liquidation", "sustainableshopping", "thrifted", "secondhand"]
    )

    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #222; font-size: 14px; }
.dep-header { background: white; border-bottom: 1px solid #e8e8e8; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; height: 58px; position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 6px rgba(0,0,0,0.07); }
.dep-logo { font-size: 24px; font-weight: 900; color: #FF2300; letter-spacing: -1px; }
.dep-nav { display: flex; gap: 24px; }
.dep-nav span { font-size: 13px; color: #555; cursor: pointer; font-weight: 500; padding: 4px 0; border-bottom: 2px solid transparent; }
.dep-nav span:hover { color: #FF2300; border-bottom-color: #FF2300; }
.demo-strip { background: #fff3e0; border-bottom: 2px solid #ffb300; color: #7a5c00; padding: 8px 24px; font-size: 12px; font-weight: 600; text-align: center; }
.container { max-width: 980px; margin: 28px auto; padding: 0 20px; display: grid; grid-template-columns: 1fr 420px; gap: 36px; }
.product-img { width: 100%; aspect-ratio: 1/1; background: linear-gradient(160deg, #ff6b6b 0%, #FF2300 45%, #c20000 100%); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 130px; position: relative; overflow: hidden; box-shadow: 0 8px 32px rgba(255,35,0,0.25); }
.product-img::after { content: 'DEMO'; position: absolute; top: 14px; left: 14px; background: rgba(255,255,255,0.2); backdrop-filter: blur(4px); color: white; font-size: 11px; font-weight: 900; padding: 5px 12px; border-radius: 100px; letter-spacing: 1px; }
.img-thumbs { display: flex; gap: 8px; margin-top: 10px; }
.img-thumb { width: 64px; height: 64px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 24px; background: #ffe5e0; border: 2px solid transparent; cursor: pointer; }
.img-thumb:first-child { border-color: #FF2300; }
.detail-col { display: flex; flex-direction: column; gap: 18px; }
.seller-row { display: flex; align-items: center; gap: 10px; }
.seller-av { width: 42px; height: 42px; background: linear-gradient(135deg, #FF2300, #ff6b6b); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 900; font-size: 16px; flex-shrink: 0; }
.seller-handle { font-weight: 700; font-size: 14px; color: #111; }
.seller-stats { font-size: 12px; color: #888; margin-top: 1px; }
.follow-btn { margin-left: auto; padding: 7px 18px; border: 2px solid #222; border-radius: 100px; font-size: 12px; font-weight: 800; background: white; cursor: not-allowed; color: #222; }
.like-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.product-title { font-size: 22px; font-weight: 800; color: #111; line-height: 1.3; }
.like-btn { font-size: 26px; cursor: pointer; background: none; border: none; flex-shrink: 0; transition: transform 0.15s; }
.like-btn:hover { transform: scale(1.2); }
.product-price { font-size: 32px; font-weight: 900; color: #FF2300; }
.dep-badges { display: flex; gap: 8px; flex-wrap: wrap; }
.dep-badge { padding: 5px 12px; border-radius: 100px; font-size: 11px; font-weight: 700; }
.desc-card { background: white; border-radius: 14px; padding: 18px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }
.desc-lbl { font-size: 10px; font-weight: 800; color: #aaa; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px; }
.desc-text { font-size: 14px; color: #444; line-height: 1.75; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.buy-card { background: white; border-radius: 14px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }
.buy-price { font-size: 28px; font-weight: 900; color: #FF2300; margin-bottom: 16px; }
.btn-buy-dep { width: 100%; padding: 16px; background: #FF2300; color: white; border: none; border-radius: 100px; font-size: 16px; font-weight: 800; cursor: not-allowed; margin-bottom: 10px; opacity: 0.85; }
.btn-offer { width: 100%; padding: 16px; background: white; color: #222; border: 2.5px solid #222; border-radius: 100px; font-size: 16px; font-weight: 700; cursor: not-allowed; }
.demo-note { text-align: center; font-size: 11px; color: #bbb; margin-top: 8px; }
.fee-note { font-size: 12px; color: #aaa; margin-top: 14px; padding-top: 14px; border-top: 1px solid #f0f0f0; line-height: 1.6; }
.dep-footer { background: #111; color: #666; padding: 20px; text-align: center; font-size: 12px; margin-top: 40px; }
.dep-footer span { color: #FF2300; font-weight: 800; }
@media (max-width: 700px) { .container { grid-template-columns: 1fr; } }
"""

    body_html = f"""
<header class="dep-header">
  <div class="dep-logo">Depop</div>
  <div class="dep-nav">
    <span>Explore</span><span>Search</span><span>Messages</span><span>Sell</span>
  </div>
</header>
<div class="demo-strip">📋 Demo Listing — Eco-Arbitrage AI &nbsp;·&nbsp; ID: {listing_id}</div>

<div class="container">
  <div class="img-col">
    <div class="product-img">{emoji}</div>
    <div class="img-thumbs">
      <div class="img-thumb">{emoji}</div>
      <div class="img-thumb">📦</div>
      <div class="img-thumb">🔍</div>
    </div>
  </div>

  <div class="detail-col">
    <div class="seller-row">
      <div class="seller-av">E</div>
      <div>
        <div class="seller-handle">@eco_arbitrage</div>
        <div class="seller-stats">⭐ 4.9 &nbsp;·&nbsp; 284 sold &nbsp;·&nbsp; Active now</div>
      </div>
      <button class="follow-btn">Follow</button>
    </div>

    <div class="like-row">
      <h1 class="product-title">{name}</h1>
      <button class="like-btn" title="Like">🤍</button>
    </div>

    <div class="product-price">${price:,.2f}</div>

    <div class="dep-badges">
      <span class="dep-badge" style="background:#e8f5e9;color:#2e7d32">{condition}</span>
      <span class="dep-badge" style="background:#e3f2fd;color:#1565c0">{category}</span>
      <span class="dep-badge" style="background:#e8f5e9;color:#2e7d32">🌿 {co2_kg}kg CO₂ saved</span>
    </div>

    <div class="desc-card">
      <div class="desc-lbl">Description</div>
      <div class="desc-text">{desc}</div>
      <div class="tags">{tags_html}</div>
    </div>

    <div class="buy-card">
      <div class="buy-price">${price:,.2f}</div>
      <button class="btn-buy-dep">Buy Now</button>
      <button class="btn-offer">Make an Offer</button>
      <div class="demo-note">🔒 Demo listing — buttons disabled</div>
      <div class="fee-note">
        Depop seller fee: ${fee:,.2f} &nbsp;·&nbsp; Net proceeds: <strong style="color:#111">${net:,.2f}</strong><br>
        SKU: <code>{sku}</code> &nbsp;·&nbsp; Listed: {deployed_at}
      </div>
    </div>
  </div>
</div>

<footer class="dep-footer">
  <span>Depop</span> &nbsp;Demo Listing &nbsp;·&nbsp; Powered by Eco-Arbitrage AI &nbsp;·&nbsp; ID: {listing_id}
</footer>"""

    return f"<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{name} | Depop</title><style>{css}</style></head><body>{body_html}</body></html>"


def _local_html(item: dict) -> str:
    name        = _html.escape(item.get("product_name", "Product"))
    price       = float(item.get("resale_price", 0))
    category    = _html.escape(item.get("category", "General"))
    emoji       = _category_emoji(item.get("category", ""))
    listing_id  = _html.escape(item.get("listing_id", ""))
    strategy    = _html.escape(item.get("strategy", ""))
    age_days    = int(item.get("age_days", 0))
    co2_kg      = item.get("co2_kg", 0)
    net         = float(item.get("net_proceeds_usd", price))
    deployed_at = str(item.get("deployed_at", ""))[:10]
    urgency     = item.get("urgency", "medium")
    sku         = _html.escape(item.get("sku", ""))

    urgency_color = {"high": "#c40000", "medium": "#e47911", "low": "#007600"}.get(urgency, "#e47911")
    urgency_bg    = {"high": "#fdecea",  "medium": "#fff3cd",  "low": "#e6f4ea" }.get(urgency, "#fff3cd")
    condition     = "Good" if age_days > 180 else "Very Good" if age_days > 90 else "Like New"
    desc          = strategy if strategy else f"Quality {category} item for local pickup or delivery. Great condition, fair price, fast transaction."

    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f7f2; color: #1a1a1a; font-size: 14px; }
.lh { background: #14532d; color: white; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; height: 60px; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 12px rgba(0,80,0,0.35); }
.lh-brand { font-size: 18px; font-weight: 900; color: #4ade80; display: flex; align-items: center; gap: 8px; }
.lh-brand small { font-size: 11px; color: #86efac; font-weight: 400; display: block; line-height: 1; margin-top: 2px; }
.lh-nav { display: flex; gap: 20px; }
.lh-nav span { font-size: 13px; color: #86efac; cursor: pointer; font-weight: 500; }
.lh-nav span:hover { color: white; }
.demo-strip { background: #dcfce7; border-bottom: 2px solid #4ade80; color: #14532d; padding: 8px 24px; font-size: 12px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
.page-wrap { max-width: 920px; margin: 28px auto; padding: 0 20px 40px; }
.back-link { font-size: 13px; color: #16a34a; cursor: pointer; margin-bottom: 16px; display: flex; align-items: center; gap: 4px; font-weight: 600; }
.listing-card { background: white; border-radius: 12px; overflow: hidden; border: 1px solid #bbf7d0; box-shadow: 0 4px 20px rgba(0,100,0,0.10); }
.card-top { display: grid; grid-template-columns: 340px 1fr; }
.card-img { background: linear-gradient(160deg, #052e16 0%, #064e3b 35%, #065f46 65%, #047857 100%); aspect-ratio: 1/1; display: flex; align-items: center; justify-content: center; font-size: 110px; position: relative; }
.card-img::after { content: 'ECO · LOCAL'; position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.45); color: rgba(255,255,255,0.85); font-size: 9px; font-weight: 900; padding: 5px 12px; border-radius: 100px; letter-spacing: 1.5px; white-space: nowrap; }
.card-details { padding: 24px 28px; display: flex; flex-direction: column; gap: 16px; }
.card-title { font-size: 24px; font-weight: 800; color: #111; line-height: 1.25; }
.card-price { font-size: 38px; font-weight: 900; color: #15803d; line-height: 1; }
.card-price small { font-size: 14px; font-weight: 500; color: #888; }
.c-badges { display: flex; gap: 8px; flex-wrap: wrap; }
.c-badge { padding: 5px 12px; border-radius: 100px; font-size: 11px; font-weight: 700; }
.card-desc { font-size: 14px; color: #555; line-height: 1.75; background: #f0fdf4; border-radius: 8px; padding: 14px 16px; border: 1px solid #bbf7d0; }
.btn-contact { width: 100%; padding: 15px; background: #15803d; color: white; border: none; border-radius: 10px; font-size: 16px; font-weight: 700; cursor: not-allowed; margin-bottom: 10px; opacity: 0.85; }
.btn-offer-l { width: 100%; padding: 15px; background: white; color: #15803d; border: 2.5px solid #15803d; border-radius: 10px; font-size: 16px; font-weight: 700; cursor: not-allowed; }
.demo-note { text-align: center; font-size: 11px; color: #bbb; margin-top: 6px; }
.card-bottom { border-top: 1px solid #d1fae5; display: grid; grid-template-columns: repeat(3, 1fr); }
.info-cell { padding: 18px 22px; border-right: 1px solid #d1fae5; }
.info-cell:last-child { border-right: none; }
.info-lbl { font-size: 10px; font-weight: 800; color: #888; text-transform: uppercase; letter-spacing: 0.7px; margin-bottom: 6px; }
.info-val { font-size: 15px; color: #111; font-weight: 700; }
.section-card { background: white; border-radius: 12px; border: 1px solid #bbf7d0; overflow: hidden; margin-top: 16px; box-shadow: 0 2px 10px rgba(0,100,0,0.06); }
.sc-head { padding: 14px 20px; background: #f0fdf4; border-bottom: 1px solid #d1fae5; font-weight: 800; font-size: 14px; color: #15803d; }
.spec-row { display: flex; border-bottom: 1px solid #f0fdf4; }
.spec-row:last-child { border-bottom: none; }
.spec-key { padding: 11px 20px; font-size: 13px; font-weight: 700; color: #333; width: 42%; border-right: 1px solid #f0fdf4; background: #f9fdf9; }
.spec-val { padding: 11px 20px; font-size: 13px; color: #555; }
.eco-card { background: white; border-radius: 12px; border: 1px solid #bbf7d0; padding: 22px; margin-top: 16px; display: flex; align-items: flex-start; gap: 16px; box-shadow: 0 2px 10px rgba(0,100,0,0.06); }
.eco-icon { font-size: 42px; flex-shrink: 0; }
.eco-title { font-size: 15px; font-weight: 800; color: #15803d; margin-bottom: 6px; }
.eco-body { font-size: 13px; color: #555; line-height: 1.7; }
.contact-card { background: white; border-radius: 12px; border: 1px solid #bbf7d0; padding: 22px; margin-top: 16px; box-shadow: 0 2px 10px rgba(0,100,0,0.06); }
.contact-head { font-weight: 800; font-size: 15px; color: #15803d; margin-bottom: 14px; }
.contact-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f0fdf4; font-size: 13px; color: #555; }
.contact-item:last-child { border-bottom: none; }
.c-icon { font-size: 20px; flex-shrink: 0; }
.l-footer { background: #052e16; color: #4ade80; padding: 20px 24px; text-align: center; font-size: 12px; margin-top: 10px; }
.l-footer span { color: #86efac; }
@media (max-width: 700px) { .card-top { grid-template-columns: 1fr; } .card-bottom { grid-template-columns: 1fr; } }
"""

    body_html = f"""
<header class="lh">
  <div class="lh-brand">🌿 EcoArbitrage Local<small>Community Marketplace</small></div>
  <nav class="lh-nav">
    <span>Browse</span><span>Sell</span><span>Sign In</span>
  </nav>
</header>
<div class="demo-strip">📋 Demo Listing — Eco-Arbitrage AI &nbsp;·&nbsp; Listing ID: {listing_id}</div>

<div class="page-wrap">
  <div class="back-link">← Back to all listings</div>

  <div class="listing-card">
    <div class="card-top">
      <div class="card-img">{emoji}</div>
      <div class="card-details">
        <h1 class="card-title">{name}</h1>
        <div class="card-price">${price:,.2f} <small>No fees · Full amount to seller</small></div>

        <div class="c-badges">
          <span class="c-badge" style="background:#dcfce7;color:#15803d">{condition}</span>
          <span class="c-badge" style="background:#dbeafe;color:#1e40af">{category}</span>
          <span class="c-badge" style="background:#fef9c3;color:#854d0e">📦 {age_days} days old</span>
          <span class="c-badge" style="background:{urgency_bg};color:{urgency_color}">⚡ {urgency.upper()} priority</span>
        </div>

        <div class="card-desc">{desc}</div>

        <div>
          <button class="btn-contact">💬 Contact Seller</button>
          <button class="btn-offer-l">💰 Make an Offer</button>
          <div class="demo-note">🔒 Demo listing — buttons disabled</div>
        </div>
      </div>
    </div>
    <div class="card-bottom">
      <div class="info-cell">
        <div class="info-lbl">📍 Location</div>
        <div class="info-val">Local · Pickup Available</div>
      </div>
      <div class="info-cell">
        <div class="info-lbl">📅 Posted</div>
        <div class="info-val">{deployed_at}</div>
      </div>
      <div class="info-cell">
        <div class="info-lbl">🌿 CO₂ Saved</div>
        <div class="info-val" style="color:#15803d">{co2_kg} kg</div>
      </div>
    </div>
  </div>

  <div class="section-card">
    <div class="sc-head">Item Details</div>
    <div class="spec-row"><div class="spec-key">Condition</div><div class="spec-val">{condition}</div></div>
    <div class="spec-row"><div class="spec-key">Category</div><div class="spec-val">{category}</div></div>
    <div class="spec-row"><div class="spec-key">SKU</div><div class="spec-val" style="font-family:monospace">{sku}</div></div>
    <div class="spec-row"><div class="spec-key">Listing ID</div><div class="spec-val" style="font-family:monospace">{listing_id}</div></div>
    <div class="spec-row"><div class="spec-key">Days in Stock</div><div class="spec-val">{age_days} days</div></div>
    <div class="spec-row"><div class="spec-key">Liquidation Priority</div><div class="spec-val"><strong style="color:{urgency_color}">{urgency.upper()}</strong></div></div>
    <div class="spec-row"><div class="spec-key">Net Proceeds</div><div class="spec-val" style="color:#15803d;font-weight:700">${net:,.2f} (0% fee)</div></div>
  </div>

  <div class="eco-card">
    <div class="eco-icon">🌍</div>
    <div>
      <div class="eco-title">Environmental Impact</div>
      <div class="eco-body">By purchasing this item locally you prevent <strong>{co2_kg} kg of CO₂</strong> equivalent from landfill waste. This listing is part of the Eco-Arbitrage circular economy initiative — resell locally, reduce globally.</div>
    </div>
  </div>

  <div class="contact-card">
    <div class="contact-head">Contact Seller (Demo)</div>
    <div class="contact-item"><span class="c-icon">💬</span><span>Message via EcoArbitrage Local app</span></div>
    <div class="contact-item"><span class="c-icon">📧</span><span>eco.local@ecoarbitrage.example.com</span></div>
    <div class="contact-item"><span class="c-icon">🤝</span><span>Safe public meetup locations available</span></div>
    <div class="contact-item"><span class="c-icon">🚚</span><span>Local delivery negotiable</span></div>
    <div class="contact-item"><span class="c-icon">💳</span><span>Cash, PayPal, or Venmo accepted</span></div>
  </div>
</div>

<footer class="l-footer">
  🌿 EcoArbitrage Local &nbsp;·&nbsp; Demo Listing &nbsp;·&nbsp; <span>ID: {listing_id}</span> &nbsp;·&nbsp; Zero platform fees · Community-first
</footer>"""

    return f"<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{name} | EcoArbitrage Local</title><style>{css}</style></head><body>{body_html}</body></html>"


def _not_found_html(listing_id: str) -> str:
    lid = _html.escape(listing_id)
    return f"""<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>Listing Not Found</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,sans-serif;background:#f5f5f5;display:flex;align-items:center;justify-content:center;min-height:100vh}}.card{{background:white;border-radius:12px;padding:48px;text-align:center;max-width:420px;box-shadow:0 4px 24px rgba(0,0,0,0.1)}}h1{{font-size:56px;margin-bottom:12px}}h2{{font-size:20px;color:#333;margin-bottom:8px}}p{{color:#888;font-size:14px;line-height:1.6;margin-bottom:20px}}code{{background:#f0f0f0;padding:2px 8px;border-radius:4px;font-size:13px}}a{{color:#0064d2;text-decoration:none;font-size:14px}}a:hover{{text-decoration:underline}}</style>
</head><body><div class="card"><h1>📭</h1><h2>Listing Not Found</h2><p>No listing with ID <code>{lid}</code> was found.<br>The server may have restarted, clearing in-memory listings.</p><a href="http://localhost:8000/ui">← Back to Eco-Arbitrage Dashboard</a></div></body></html>"""


def generate_listing_html(item: dict) -> str:
    platform = item.get("platform", "local")
    if platform == "ebay":
        return _ebay_html(item)
    elif platform == "depop":
        return _depop_html(item)
    else:
        return _local_html(item)


@app.get("/listing/{listing_id}", response_class=HTMLResponse)
def view_listing(listing_id: str):
    """Serve a styled listing page for a deployed item."""
    item = next((d for d in _deployed_items if d.get("listing_id") == listing_id), None)
    if not item:
        return HTMLResponse(_not_found_html(listing_id), status_code=404)
    return HTMLResponse(generate_listing_html(item))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
