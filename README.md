#  Eco-Arbitrage AI

## AI-Powered Inventory Value Recovery & Liquidation System

**Built for HCBC Hackathon 2026 | Theme: "AI for a Smarter Tomorrow"**

---

##  Project Overview

Eco-Arbitrage is an autonomous AI-powered inventory liquidation platform that transforms unsold stock ("dead inventory") into liquid capital while preventing environmental waste. The system uses AI-driven pricing optimization and automated marketplace deployment to recover maximum value from overstock items.

---

##  Key Features

###  AI Liquidation Engine
- **Smart Detection**: Automatically flags inventory stored 90+ days
- **AI Pricing**: Uses Groq LLaMA 3.3 70B for intelligent pricing
- **Auto-Copywriter**: Generates SEO-optimized product descriptions
- **Urgency Classification**: High/Medium/Low priority indicators
- **Streaming Results**: Real-time progress visualization

###  Dashboard & Analytics
- KPI Cards: Total Inventory, Overstock Items, Critical Stock, At-Risk Items
- Value Metrics: Total Value (USD), Waste Footprint (kg CO₂)
- Filter by: Product name, inventory age, category
- Real-time stats updates

###  Marketplace Scraper
- Scrape Amazon, eBay, Etsy product data
- Configurable pages (1-5)
- Auto-generates importable CSV files

###  Data Management
- CSV file upload with validation
- Auto-extract categories from data
- Sample data included (30+ products)

###  One-Click Deployment
- **eBay**: Fixed-price GTC listings (13.25% fee)
- **Depop**: BuyNow listings (10% + $0.30 fee)
- **Local**: Internal marketplace (0% fee)

###  Platform Listing Pages
- eBay-style product page
- Depop-style social listing
- Local marketplace pickup UI

---

##  Tech Stack

| Layer | Technology |
|-------|----------|
| Frontend | Pure HTML/CSS/JS |
| Backend | FastAPI (Python 3.11+) |
| AI Engine | Groq LLaMA 3.3 70B |
| Scraping | BeautifulSoup + ScraperAPI |
| Data | Pandas + CSV |

---

##  Project Structure

```
eco-arbitrage/
├── README.md                  # This file
├── START_HACKATHON.md        # Hackathon starter template
├── .gitignore             # Git ignore patterns
├── docs/
│   └── README.md          # Documentation folder
├── demo/
│   └── .gitkeep         # Demo screenshots
└── src/
    ├── index.html      # Frontend dashboard
    ├── api.py       # FastAPI backend
    ├── agent.py     # Groq AI agent
    ├── scraper.py   # Web scraper
    ├── requirements.txt
    ├── data.csv    # Sample inventory (dishwashers)
    ├── data_1.csv  # Additional inventory
    └── uploads/    # Uploaded CSV files
```

---

##  Setup Instructions

### Prerequisites
- Python 3.11+
- API key for Groq (free at console.groq.com)

### 1. Clone Repository
```bash
git clone https://github.com/samnabingg/TeamRainbow-HCBC-Hackathon-Project
cd eco-arbitrage
```

### 2. Install Dependencies
```bash
pip install -r src/requirements.txt
```

### 3. Configure API Key
Create `src/.env`:
```env
GROQ_API_KEY=your_groq_api_key_here
SCRAPER_API_KEY=your_scraperapi_key_here  # optional
```

### 4. Run Backend
```bash
cd src
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Access Dashboard
- Web UI: http://localhost:8000/ui
- API Base: http://localhost:8000

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/ui` | Frontend dashboard |
| GET | `/inventory` | Get filtered inventory |
| GET | `/categories` | Get unique categories |
| GET | `/stats` | Get KPI stats |
| POST | `/optimize` | Run AI optimizer (streaming) |
| POST | `/upload` | Upload CSV file |
| POST | `/scrape` | Scrape marketplace |
| POST | `/deploy` | Deploy to marketplace |
| GET | `/deployments` | Get all deployments |
| GET | `/listing/{id}` | View listing page |

---

##  Data Format

### CSV Columns Required
```csv
product_id,product_name,category,original_cost_usd,inventory_age_days,waste_footprint_kg,stock_level
B001,Product Name,Category,29.99,120,0.9,15
```

---

##  Business Impact

| Metric | Value |
|--------|-------|
| Recovery Rate | 40-60% of original cost |
| Processing Time | Hours → Seconds |
| Platform Reach | eBay, Depop, Local |

---

## 👥 Team

Developed for **HCBC Hackathon 2026** 

| Members | 
|--------|
| **Samana** | 
| **Binanshika**|
| **Poonam** | 
| **Ashrika** | 
---------

##  Future Work

- Real Shopify/Amazon API integration
- AI product image enhancement
- Real-time market trend analysis
- Multi-channel: Mercari, Poshmark, StockX

---

##  License

MIT License

---

*Built for HCBC Hackathon 2026*  
*Theme: AI for a Smarter Tomorrow*
