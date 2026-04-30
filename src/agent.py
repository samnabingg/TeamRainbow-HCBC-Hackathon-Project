import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def process_item(item):
    # Updated prompt to match 'real_inventory_data.csv' columns
    # Added 'waste_footprint_kg' to leverage the 'Eco' aspect in descriptions
    prompt = f"""
    You are an AI agent specializing in Eco-Arbitrage and inventory recovery.
    Your goal is to liquidate dead stock while highlighting its environmental value.

    Item: {item['product_name']}
    Category: {item['category']}
    Original Cost: ${item['original_cost_usd']}
    Inventory Age: {item['inventory_age_days']} days
    Waste Footprint: {item['waste_footprint_kg']}kg (CO2e/Waste prevented by reselling)

    Tasks:
    1. Classify liquidation urgency (high, medium, low) based on age.
    2. Suggest a competitive resale price.
    3. Write a 2-sentence description focusing on the item's quality and the eco-benefit of buying it instead of it going to a landfill.

    Return ONLY valid JSON:
    {{
        "urgency": "high/medium/low",
        "resale_price": number,
        "description": "text"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            # Ensuring the model returns a valid JSON object
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
    
    except Exception as e:
        # Fallback if the API fails or JSON is malformed
        return {
            "urgency": "medium",
            "resale_price": round(item['original_cost_usd'] * 0.7, 2),
            "description": f"Great {item['product_name']} looking for a new home to reduce waste."
        }

if __name__ == "__main__":
    # Test with new data format
    test_item = {
        "product_name": "Recycled Polyester Jacket",
        "category": "Apparel",
        "original_cost_usd": 120.0,
        "inventory_age_days": 110,
        "waste_footprint_kg": 4.5
    }
    result = process_item(test_item)
    print(json.dumps(result, indent=2))
