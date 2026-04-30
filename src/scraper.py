import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
from dotenv import load_dotenv

load_dotenv()
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")

def make_request(url):
    """Route any URL through ScraperAPI"""
    proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={url}"
    return requests.get(proxy_url, timeout=30)

# ── AMAZON ──────────────────────────────────────────
def scrape_amazon(keyword, pages=2):
    results = []
    for page in range(1, pages + 1):
        url = f"https://www.amazon.com/s?k={keyword}&page={page}"
        r = make_request(url)
        soup = BeautifulSoup(r.text, 'html.parser')

        for item in soup.select('[data-component-type="s-search-result"]'):
            try:
                name = item.select_one('h2 span').text.strip()
                asin = item.get('data-asin', '')
                price_el = item.select_one('.a-price .a-offscreen')
                price = float(price_el.text.replace('$','').replace(',','')) if price_el else 0
                results.append({
                    'product_id': asin,
                    'product_name': name,
                    'category': keyword,
                    'original_cost_usd': price,
                    'inventory_age_days': random.randint(30, 200),
                    'waste_footprint_kg': round(price * 0.03, 2),
                    'stock_level': random.randint(1, 50)
                })
            except:
                continue
        time.sleep(2)
    return pd.DataFrame(results)

# ── EBAY ─────────────────────────────────────────────
def scrape_ebay(keyword, pages=2):
    results = []
    for page in range(1, pages + 1):
        url = f"https://www.ebay.com/sch/i.html?_nkw={keyword}&_pgn={page}"
        r = make_request(url)
        soup = BeautifulSoup(r.text, 'html.parser')

        for item in soup.select('.s-item'):
            try:
                name = item.select_one('.s-item__title').text.strip()
                if name == "Shop on eBay":
                    continue
                price_text = item.select_one('.s-item__price').text.strip()
                price = float(price_text.replace('$','').replace(',','').split()[0])
                item_id = item.select_one('.s-item__link')['href'].split('/')[4].split('?')[0]
                results.append({
                    'product_id': f"EBAY-{item_id}",
                    'product_name': name,
                    'category': keyword,
                    'original_cost_usd': price,
                    'inventory_age_days': random.randint(30, 200),
                    'waste_footprint_kg': round(price * 0.03, 2),
                    'stock_level': random.randint(1, 50)
                })
            except:
                continue
        time.sleep(2)
    return pd.DataFrame(results)

# ── ETSY ──────────────────────────────────────────────
def scrape_etsy(keyword, pages=2):
    results = []
    for page in range(1, pages + 1):
        url = f"https://www.etsy.com/search?q={keyword}&page={page}"
        r = make_request(url)
        soup = BeautifulSoup(r.text, 'html.parser')

        for item in soup.select('[data-listing-id]'):
            try:
                name = item.select_one('[data-listing-id] h3').text.strip()
                listing_id = item.get('data-listing-id', '')
                price_el = item.select_one('.currency-value')
                price = float(price_el.text.replace(',','')) if price_el else 0
                results.append({
                    'product_id': f"ETSY-{listing_id}",
                    'product_name': name,
                    'category': keyword,
                    'original_cost_usd': price,
                    'inventory_age_days': random.randint(30, 200),
                    'waste_footprint_kg': round(price * 0.03, 2),
                    'stock_level': random.randint(1, 50)
                })
            except:
                continue
        time.sleep(2)
    return pd.DataFrame(results)

# ── ROUTER ────────────────────────────────────────────
def scrape(source, keyword, pages=2):
    scrapers = {
        "amazon": scrape_amazon,
        "ebay":   scrape_ebay,
        "etsy":   scrape_etsy,
    }
    fn = scrapers.get(source.lower())
    if not fn:
        raise ValueError(f"Unknown source: {source}")
    return fn(keyword, pages)