# Zhou-Mukamuri AI-Driven Logistics Demo
AI-Enabled Sustainable Agricultural Logistics Optimisation for Informal Markets in South Africa

## Overview
This repository demonstrates a complete, explainable **AI-driven logistics optimisation system** designed to improve smallholder supply chains and informal agricultural markets in South Africa.  
It supports the research work titled **“Artificial Intelligence-Driven Sustainable Logistics for Informal Agricultural Markets in Southern Africa”**, led by the Zhou–Mukamuri Research Team under Quantilytix Labs.

The system integrates three main parts:
1. **Data Extraction** — Uses a Large Language Model (Gemini 2.0 Flash) to read farmer messages (from CSV/Excel) and convert them into structured data (e.g., “who has what, where, and when”).
2. **AI Planning Engine** — Uses mathematical optimisation (Google OR-Tools) to plan efficient routes for collecting and delivering produce.
3. **Interactive Simulation** — Uses a visual map (React + Leaflet) to replay the optimised routes in 90 seconds, showing deliveries and performance metrics.

---

## System Architecture

### Data Flow Diagram
```
Farmer Messages (CSV/Excel)
        ↓
  /extract  →  Gemini-2.0-Flash  →  Structured "lots" (crop, kg, location, time)
        ↓
  /plan  →  OR-Tools Solver  →  Hub Assignment + Vehicle Routing + KPIs
        ↓
   React Frontend (Lovable.dev) → KPI Dashboard + Map Playback
```

---

## Server (Flask Backend)

### Purpose
The backend handles all the “thinking” in this demo — it reads messages, calls the AI model, computes logistics plans, and returns data to the frontend.  
It is written in **Python**, using **Flask**, a lightweight web framework.

---

### Folder Structure
```
/app
  ├── main.py               # Main Flask application and all endpoints
  ├── requirements.txt       # List of Python libraries needed
  ├── sample_data.csv        # Example dataset of farmer messages
```

---

## Explanation of Key Libraries

### 1. Flask
Flask is a simple and flexible Python web framework used to create web servers and APIs.  
It provides routes such as `/extract` and `/plan` that the frontend can call.  
Think of Flask as the bridge between the user interface and the AI logic.

### 2. Flask-CORS
CORS (Cross-Origin Resource Sharing) allows web applications hosted on other domains (like the Lovable frontend) to communicate with this Flask API safely.  
Without this, browsers would block data requests between different URLs.

### 3. pandas
Pandas is a data analysis library that reads Excel or CSV files easily and represents them as structured tables.  
It is used here to read farmer message files, clean them, and pass them to the Gemini model.

### 4. google-generativeai
This is the official Python SDK to connect to Google’s Gemini LLM (Large Language Model).  
It allows the server to send structured prompts and receive intelligent, formatted responses — in this case, converting informal farmer text messages into clean logistics data.

### 5. OR-Tools
Google OR-Tools is an operations research and optimisation library.  
It handles problems like the Vehicle Routing Problem (VRP) — finding the shortest path for trucks to collect and deliver goods under time and capacity limits.  
The library runs the mathematical solver that calculates the optimal routes for this demo.

### 6. numpy
Numpy provides mathematical tools for working with numbers, arrays, and matrices efficiently.  
In this system, it helps compute distances and travel times between farms, hubs, and markets.

### 7. logging
Python’s built-in logging library records key events, errors, and model outputs.  
It helps track how much produce was processed, whether constraints were met, and if the model encountered any errors.

---

## API Routes (Server Endpoints)

### `GET /health`
Checks the system’s health and the current Gemini model version.
```json
{
  "status": "ok",
  "time": "2025-11-03T09:00:00Z",
  "model": "gemini-2.0-flash"
}
```

---

### `GET /profiles`
Returns preset optimisation profiles (cost, freshness, emissions balance).
```json
{
  "low_cost": {"E_cap":1200.0,"S_cap_pct":8.0,"R_min_pct":90.0},
  "freshness_first": {"E_cap":2000.0,"S_cap_pct":2.0,"R_min_pct":95.0},
  "low_carbon": {"E_cap":800.0,"S_cap_pct":10.0,"R_min_pct":85.0}
}
```
Each profile defines sustainability trade-offs:
- **E_cap**: Maximum CO₂ emissions allowed  
- **S_cap_pct**: Spoilage cap (percent of produce that can spoil)  
- **R_min_pct**: Minimum required service rate (deliveries completed)

---

### `POST /ingest`
Uploads a CSV or Excel file of farmer messages for preview.  
Each file must have columns:
- `message_id`
- `sender_phone`
- `timestamp_local`
- `message_text`

Returns:
- A preview of the first 50 messages  
- Total number of messages

---

### `POST /extract`
Uses the Gemini-2.0-Flash LLM to automatically interpret farmer messages.  
It extracts structured information: who the farmer is, what they are selling, how much, where, and when.

**Process:**
1. The uploaded CSV or Excel file is read with pandas.  
2. Each message is sent to Gemini with a custom extraction prompt.  
3. Gemini returns structured data (in JSON format).  
4. The system fills missing locations using known KwaZulu-Natal places.  
5. The final list of “lots” (produce offers) is returned for planning.

**Example Output:**
```json
{
  "lots": [
    {
      "message_id": "1",
      "phone": "27821234567",
      "location_text": "Umlazi",
      "geo": {"lat": -29.97, "lon": 30.878, "quality": "matched"},
      "crop_items": [{"crop": "tomatoes", "kg_estimate": 400}],
      "availability_window": {"start_local": "2025-11-03T07:00:00", "end_local": "2025-11-03T12:00:00"},
      "intent": "offer"
    }
  ]
}
```

---

### `POST /plan`
Runs the optimisation engine.  
It takes the extracted “lots” and generates a logistics plan — which hubs to use, what vehicles to send, and when.

**Process Overview:**
1. Groups all lots into farm points with location and quantity.  
2. Assigns each farm to the nearest available logistics hub (Pretoria, Durban, Stellenbosch).  
3. Builds a Vehicle Routing Problem (VRP) model using OR-Tools.  
4. Calculates route cost, distance, emissions, and spoilage.  
5. Returns clear key performance indicators (KPIs) and a readable decision summary.

**Example Output:**
```json
{
  "kpis": {
    "total_cost_zar": 536,
    "total_emissions_kg": 44.9,
    "total_distance_km": 40.3,
    "delivered_kg": 1747.5,
    "service_rate_pct": 90.1,
    "spoilage_pct_proxy": 4.7
  },
  "decision_brief": [
    "Service minimum not met: add capacity or relax windows."
  ]
}
```

---

## Frontend Overview (Lovable.dev)

**Technologies Used:**
- **React + TypeScript** — Handles user interface and state management.  
- **React-Leaflet** — Displays an interactive map and plays the 90-second delivery simulation.  
- **Ant Design (AntD)** — Used for cards, buttons, and layout styling.  

**Features:**
- Upload CSV → see message preview  
- Extract structured data via Gemini  
- Choose an optimisation profile  
- Generate plan → see KPIs and map routes  
- Play the 90-second simulation showing vehicle movement  

---

## How to Run Locally

### 1. Clone the Repository
```
git clone https://github.com/<your-org>/zhou-mukamuri-ai-logistics-demo.git
cd zhou-mukamuri-ai-logistics-demo
```

### 2. Install Dependencies
```
pip install -r requirements.txt
```

### 3. Set Environment Variables
```
export GEMINI_API_KEY="your_api_key_here"
export PORT=7860
```

### 4. Run the Flask Server
```
python main.py
```
The server will start on:
```
http://localhost:7860
```

---

## Example Dataset
The repository includes `sample_data.csv` with farmer messages from KwaZulu-Natal.

Example:
```
message_id,sender_phone,timestamp_local,message_text
1,+27821234567,2025-11-03T06:30:00,"I have 25 crates of tomatoes from Umlazi ready by 8am"
2,+27829876543,2025-11-03T07:00:00,"Pinetown farmer here, 40 bags of potatoes available after 10am"
```

---

## Deployment
- Hosted backend: [https://rairo-agri-ai.hf.space](https://rairo-agri-ai.hf.space)
- Frontend (Lovable.dev): displays metrics and interactive simulation  
- Deployment platform: Hugging Face Spaces (port 7860)

---

## Citation
If you reference this demo or its research output, please cite:
> Zhou-Mukamuri, et al. (2025). *Artificial Intelligence-Driven Sustainable Logistics for Informal Agricultural Markets in Southern Africa*. Quantilytix Research Lab.

---

## License
MIT License © 2025 Quantilytix / Zhou–Mukamuri Research Team
