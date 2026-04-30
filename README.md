#  Eco-Arbitrage: AI-Powered Value Recovery

**Built for HCBC Hackathon 2026 | Theme: "AI for a Smarter Tomorrow"**

Eco-Arbitrage is an automated workflow designed to solve a multi-billion dollar problem: **unsold inventory.** By combining AI-driven logistics with circular economy principles, this tool transforms "dead stock" into liquid capital and prevents environmental waste.

---

##  The Vision
E-commerce businesses lose millions to "shrink" and storage costs for items that sit idle. Eco-Arbitrage acts as an **Autonomous Resale Agent** that:
1. **Identifies** slow-moving stock before it becomes a total loss.
2. **Optimizes** resale pricing using AI logic.
3. **Automates** the creation of marketplace-ready listings.

---

##  Key Features
- **Smart Detection:** Automatically flags inventory stored for over 90 days.
- **AI Pricing Engine:** Estimates the "Sweet Spot" price to ensure quick liquidation while maintaining margins.
- **Auto-Copywriter:** Generates SEO-optimized product descriptions for platforms like Poshmark or eBay.
- **Impact Dashboard:** Real-time visualization of **Recovered Value ($)** and **Waste Prevented (kg)**.
- **Agentic Workflow:** Simulated "One-Click" posting to secondary marketplaces.

---

##  Tech Stack
*   **Frontend:** [Streamlit](https://streamlit.io) (Rapid UI Deployment)
*   **Intelligence:** [OpenAI API](https://openai.com) (GPT-4o for pricing & copy)
*   **Data:** [Pandas](https://pydata.org) (Inventory Analysis)
*   **Backend:** Python 3.11+

---

##  Project Structure
```text
eco-arbitrage/
├── demo/                # Demo videos & UI screenshots
├── src/
│   ├── app.py           # Main Streamlit UI
│   ├── agent.py         # AI Logic & OpenAI Integration
│   └── data.csv         # Mock Inventory Dataset
├── .env                 # API Keys (GitIgnored)
└── README.md
```

---

##  Setup Instructions

### 1. Clone & Enter
```bash
git clone https://github.com/samnabingg/TeamRainbow-HCBC-Hackathon-Project
cd eco-arbitrage
```

### 2. Install Dependencies
```bash
pip install pandas openai streamlit python-dotenv
```

### 3. Configure API Key
Create a `.env` file in the `src/` directory:
```env
OPENAI_API_KEY=your_actual_key_here
```

### 4. Launch the App
```bash
streamlit run src/app.py
```

---

## Business Impact
- **Recovery:** Recovers up to 40-60% of original cost on items usually destined for landfills.
- **Efficiency:** Reduces the time spent on manual liquidation from hours to seconds.
- **Sustainability:** Directly contributes to **Circular Economy** goals by extending product lifecycles.

---

##  Limitations & Future Work
*   **Current:** Uses static CSV data and simulated marketplace APIs.
*   **Future:** Integration with **Shopify/Amazon APIs**, real-time market trend analysis, and automated image enhancement for listings.

---

##  The Team
Developed in **10 Hours** for the HCBC Hackathon 2026. 
Members: Samana Dahal, Poonam Bhandari, Ashrika Ranjit
*Focus: AI Strategy, Software Automation, and Business Sustainability.*
