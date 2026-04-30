import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def process_item(item):
    prompt = f"""
    You are an AI agent helping liquidate overstock inventory.

    Item: {item['Item Name']}
    Original Price: {item['Original Price']}

    Tasks:
    1. Classify urgency (high, medium, low)
    2. Suggest resale price for quick sale
    3. Write a 2-sentence product description

    Return ONLY valid JSON:
    {{
        "urgency": "high/medium/low",
        "resale_price": number,
        "description": "text"
    }}
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except:
        return {
            "urgency": "unknown",
            "resale_price": 0,
            "description": content
        }
    
if __name__ == "__main__":
    test_item = {
        "Item Name": "Denim Jacket",
        "Original Price": 80
    }

    result = process_item(test_item)
    print(result)