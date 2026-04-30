# pip install requests beautifulsoup4 pandas
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import os
from dotenv import load_dotenv

load_dotenv()
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")

def scrape_amazon_search(keyword, pages=3):
    results = []
    
    for page in range(1, pages + 1):
        url = f"https://www.amazon.com/s?k={keyword}&page={page}"
        
        # Route through ScraperAPI to bypass blocks
        proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={url}"
        
        r = requests.get(proxy_url, timeout=30)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for item in soup.select('[data-component-type="s-search-result"]'):
            try:
                name = item.select_one('h2 span').text.strip()
                asin = item.get('data-asin', '')
                
                price_el = item.select_one('.a-price .a-offscreen')
                price = float(price_el.text.replace('$','').replace(',','')) if price_el else 0
                
                rating_el = item.select_one('.a-icon-alt')
                rating = rating_el.text.split()[0] if rating_el else '0'
                
                results.append({
                    'product_id': asin,
                    'product_name': name,
                    'category': keyword,
                    'original_cost_usd': price,
                    'inventory_age_days': random.randint(30, 200),  # simulated
                    'waste_footprint_kg': round(price * 0.03, 2),   # estimated
                    'stock_level': random.randint(1, 50)
                })
            except:
                continue
        
        time.sleep(2)  # be polite
    
    return pd.DataFrame(results)

# Run it
df = scrape_amazon_search("electronics overstock", pages=3)
df.to_csv("data.csv", index=False)
print(f"Saved {len(df)} products to data.csv")