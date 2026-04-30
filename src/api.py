"""
FastAPI Backend for Eco-Arbitrage
Replaces Streamlit with REST API serving agent.py logic
"""

import os
import json
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse

# Import the AI agent
from agent import process_item


# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data on startup, cleanup on shutdown"""
    load_data()
    yield
    # Cleanup code here if needed


app = FastAPI(
    title="Eco-Arbitrage API",
    description="AI-Powered Inventory Recovery & Liquidation Engine",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global dataframe storage
_df = None
_default_csv_path = os.path.join(os.path.dirname(__file__), "data.csv")


def load_data(csv_path: Optional[str] = None) -> pd.DataFrame:
    """Load inventory data from CSV"""
    global _df
    path = csv_path or _default_csv_path
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Data file not found: {path}")
    
    _df = pd.read_csv(path)
    return _df


def get_dataframe() -> pd.DataFrame:
    """Get current dataframe or load default"""
    global _df
    if _df is None:
        return load_data()
    return _df


# ============ ENDPOINTS ============

@app.get("/")
def root():
    """Root endpoint"""
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
            "GET /categories": "Get unique categories"
        }
    }


@app.get("/inventory")
def get_inventory(
    min_age: int = Query(0, ge=0, description="Minimum inventory age in days"),
    max_age: int = Query(500, ge=0, description="Maximum inventory age in days"),
    categories: Optional[str] = Query(None, description="Comma-separated categories to filter"),
    search: Optional[str] = Query(None, description="Search term for product name")
):
    """
    GET /inventory - Returns filtered CSV data as JSON
    """
    df = get_dataframe()
    
    # Apply filters
    filtered = df[
        (df["inventory_age_days"] >= min_age) &
        (df["inventory_age_days"] <= max_age)
    ]
    
    if categories:
        category_list = [c.strip() for c in categories.split(",")]
        filtered = filtered[filtered["category"].isin(category_list)]
    
    if search:
        filtered = filtered[
            filtered["product_name"].str.contains(search, case=False, na=False)
        ]
    
    # Convert to JSON-friendly format
    result = filtered.to_dict(orient="records")
    
    return {
        "success": True,
        "count": len(result),
        "data": result
    }


@app.get("/categories")
def get_categories():
    """Get unique categories"""
    df = get_dataframe()
    categories = df["category"].unique().tolist()
    return {
        "success": True,
        "categories": sorted(categories)
    }

@app.get("/ui")
def serve_frontend():
    """Serve the index.html frontend"""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(html_path)


@app.get("/stats")
def get_stats(
    min_age: int = Query(90, ge=0, description="Minimum inventory age for overstock")
):
    """
    GET /stats - Returns KPI summary
    """
    df = get_dataframe()
    
    # Calculate overstock (items older than min_age)
    overstock = df[df["inventory_age_days"] >= min_age]
    
    # Calculate statistics
    total_inventory = len(df)
    overstock_count = len(overstock)
    total_original_cost = df["original_cost_usd"].sum()
    total_waste_footprint = df["waste_footprint_kg"].sum()
    overstock_cost = overstock["original_cost_usd"].sum()
    overstock_waste = overstock["waste_footprint_kg"].sum()
    
    # Category breakdown
    category_counts = df["category"].value_counts().to_dict()
    
    return {
        "success": True,
        "stats": {
            "total_inventory": total_inventory,
            "overstock_items": overstock_count,
            "total_value": round(total_original_cost, 2),
            "total_waste_footprint_kg": round(total_waste_footprint, 2),
            "overstock_value": round(overstock_cost, 2),
            "overstock_waste_kg": round(overstock_waste, 2),
            "category_breakdown": category_counts,
            "at_risk_items": len(df[df["inventory_age_days"] >= 120]),
            "critical_items": len(df[df["inventory_age_days"] >= 180])
        }
    }


class OptimizerIterator:
    """Iterator for streaming AI optimization results"""
    
    def __init__(self, items: List[Dict[str, Any]]):
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
        
        # Process item through AI
        ai_result = process_item(item)
        
        # Calculate profit
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
        
        # Format as SSE (Server-Sent Events)
        return f"data: {json.dumps(result)}\n\n"
    
    def get_final_results(self):
        return self.results


@app.post("/optimize")
async def run_optimization(
    min_age: int = Query(90, ge=0, description="Minimum inventory age"),
    categories: Optional[str] = Query(None, description="Comma-separated categories to filter")
):
    """
    POST /optimize - Runs agent.py on selected items with streaming response
    """
    df = get_dataframe()
    
    # Filter items
    filtered = df[df["inventory_age_days"] >= min_age]
    
    if categories:
        category_list = [c.strip() for c in categories.split(",")]
        filtered = filtered[filtered["category"].isin(category_list)]
    
    if len(filtered) == 0:
        raise HTTPException(
            status_code=400,
            detail="No items match the current filters"
        )
    
    # Convert to list of dicts
    items = filtered.to_dict(orient="records")
    
    # Create streaming response
    async def generate():
        iterator = OptimizerIterator(items)
        
        try:
            for line in iterator:
                yield line
                # Small delay between items for visual effect
                await asyncio.sleep(0.1)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        # Send final summary
        results = iterator.get_final_results()
        total_profit = sum(r["est_profit"] for r in results)
        total_co2 = sum(r["co2_impact_kg"] for r in results)
        
        final_summary = {
            "done": True,
            "total_processed": len(results),
            "total_profit": round(total_profit, 2),
            "total_co2_kg": round(total_co2, 2),
            "high_urgency": len([r for r in results if r["urgency"] == "high"]),
            "medium_urgency": len([r for r in results if r["urgency"] == "medium"]),
            "low_urgency": len([r for r in results if r["urgency"] == "low"])
        }
        
        yield f"data: {json.dumps(final_summary)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@app.post("/optimize-single")
def optimize_single_item(item: Dict[str, Any]):
    """
    POST /optimize-single - Process a single item (non-streaming)
    """
    try:
        result = process_item(item)
        result["success"] = True
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    POST /upload - Upload a new CSV file
    """
    global _df, _default_csv_path
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are accepted"
        )
    
    # Save uploaded file
    upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(upload_dir, f"inventory_{timestamp}.csv")
    
    content = await file.read()
    with open(file_path, 'wb') as f:
        f.write(content)
    
    # Load and validate the CSV
    try:
        df = pd.read_csv(file_path)
        
        # Validate required columns
        required_columns = [
            'product_id', 'product_name', 'category', 
            'inventory_age_days', 'original_cost_usd', 'waste_footprint_kg'
        ]
        
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required columns: {missing}"
            )
        
        # Update global dataframe
        _df = df
        _default_csv_path = file_path
        
        return {
            "success": True,
            "message": "CSV uploaded successfully",
            "filename": file.filename,
            "row_count": len(df),
            "categories": df["category"].unique().tolist()
        }
        
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=400,
            detail="The uploaded CSV file is empty"
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error processing CSV: {str(e)}"
        )


@app.post("/reset")
def reset_to_default():
    """Reset to default data.csv"""
    global _df, _default_csv_path
    _default_csv_path = os.path.join(os.path.dirname(__file__), "data.csv")
    _df = pd.read_csv(_default_csv_path)
    return {
        "success": True,
        "message": "Reset to default dataset",
        "row_count": len(_df)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
