import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import logging
from dotenv import load_dotenv

load_dotenv()
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")
logger = logging.getLogger(__name__)


def make_request(url: str) -> requests.Response:
    """Route any URL through ScraperAPI with validation."""
    if not SCRAPER_API_KEY:
        raise EnvironmentError(
            "SCRAPER_API_KEY is not set. Add it to your .env file."
        )
    proxy_url = (
        f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={url}"
    )
    r = requests.get(proxy_url, timeout=30)
    r.raise_for_status()  # raises HTTPError on 4xx/5xx from ScraperAPI itself
    return r


# ── AMAZON ──────────────────────────────────────────
def scrape_amazon(keyword: str, pages: int = 2) -> pd.DataFrame:
    results = []
    for page in range(1, pages + 1):
        url = f"https://www.amazon.com/s?k={keyword}&page={page}"
        try:
            r = make_request(url)
        except Exception as e:
            logger.error(f"Amazon request failed (page {page}): {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select('[data-component-type="s-search-result"]')
        logger.info(f"Amazon page {page}: found {len(items)} raw items")

        for item in items:
            try:
                name = item.select_one("h2 span")
                if not name:
                    continue
                name = name.text.strip()

                asin = item.get("data-asin", "")
                if not asin:
                    continue

                price_el = item.select_one(".a-price .a-offscreen")
                price = (
                    float(price_el.text.replace("$", "").replace(",", ""))
                    if price_el
                    else 0.0
                )

                results.append({
                    "product_id": asin,
                    "product_name": name,
                    "category": keyword,
                    "original_cost_usd": price,
                    "inventory_age_days": random.randint(30, 200),
                    "waste_footprint_kg": round(price * 0.03, 2),
                    "stock_level": random.randint(1, 50),
                })
            except Exception as e:
                logger.warning(f"Amazon item parse error: {e}")
                continue

        time.sleep(2)

    return pd.DataFrame(results)


# ── EBAY ─────────────────────────────────────────────
def _parse_ebay_price(price_text: str) -> float:
    """Handle single prices and ranges like '$10.00 to $20.00'."""
    # Take the first price token only
    token = price_text.replace(",", "").strip().split()[0]
    return float(token.replace("$", ""))


def _parse_ebay_item_id(href: str) -> str:
    """Extract item ID from eBay URL robustly."""
    # URLs look like: https://www.ebay.com/itm/TITLE/123456789?...
    # or: https://www.ebay.com/itm/123456789?...
    parts = href.split("?")[0].rstrip("/").split("/")
    # The item ID is the last all-numeric segment
    for part in reversed(parts):
        if part.isdigit():
            return part
    return parts[-1]  # fallback


def scrape_ebay(keyword: str, pages: int = 2) -> pd.DataFrame:
    results = []
    for page in range(1, pages + 1):
        url = f"https://www.ebay.com/sch/i.html?_nkw={keyword}&_pgn={page}"
        try:
            r = make_request(url)
        except Exception as e:
            logger.error(f"eBay request failed (page {page}): {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select(".s-item")
        logger.info(f"eBay page {page}: found {len(items)} raw items")

        for item in items:
            try:
                title_el = item.select_one(".s-item__title")
                if not title_el:
                    continue
                name = title_el.text.strip()
                if name in ("Shop on eBay", ""):
                    continue

                price_el = item.select_one(".s-item__price")
                if not price_el:
                    continue
                price = _parse_ebay_price(price_el.text.strip())

                link_el = item.select_one(".s-item__link")
                if not link_el or not link_el.get("href"):
                    continue
                item_id = _parse_ebay_item_id(link_el["href"])

                results.append({
                    "product_id": f"EBAY-{item_id}",
                    "product_name": name,
                    "category": keyword,
                    "original_cost_usd": price,
                    "inventory_age_days": random.randint(30, 200),
                    "waste_footprint_kg": round(price * 0.03, 2),
                    "stock_level": random.randint(1, 50),
                })
            except Exception as e:
                logger.warning(f"eBay item parse error: {e}")
                continue

        time.sleep(2)

    return pd.DataFrame(results)


# ── ETSY ──────────────────────────────────────────────
def scrape_etsy(keyword: str, pages: int = 2) -> pd.DataFrame:
    results = []
    for page in range(1, pages + 1):
        url = f"https://www.etsy.com/search?q={keyword}&page={page}"
        try:
            r = make_request(url)
        except Exception as e:
            logger.error(f"Etsy request failed (page {page}): {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("[data-listing-id]")
        logger.info(f"Etsy page {page}: found {len(items)} raw items")

        for item in items:
            try:
                # Etsy renders h3 directly inside the listing card
                name_el = item.select_one("h3")
                if not name_el:
                    continue
                name = name_el.text.strip()

                listing_id = item.get("data-listing-id", "")
                if not listing_id:
                    continue

                price_el = item.select_one(".currency-value")
                price = (
                    float(price_el.text.replace(",", "")) if price_el else 0.0
                )

                results.append({
                    "product_id": f"ETSY-{listing_id}",
                    "product_name": name,
                    "category": keyword,
                    "original_cost_usd": price,
                    "inventory_age_days": random.randint(30, 200),
                    "waste_footprint_kg": round(price * 0.03, 2),
                    "stock_level": random.randint(1, 50),
                })
            except Exception as e:
                logger.warning(f"Etsy item parse error: {e}")
                continue

        time.sleep(2)

    return pd.DataFrame(results)


# ── ROUTER ────────────────────────────────────────────
def scrape(source: str, keyword: str, pages: int = 2) -> pd.DataFrame:
    scrapers = {
        "amazon": scrape_amazon,
        "ebay": scrape_ebay,
        "etsy": scrape_etsy,
    }
    fn = scrapers.get(source.lower())
    if not fn:
        raise ValueError(f"Unknown source: {source}. Choose from: {list(scrapers)}")
    return fn(keyword, pages)