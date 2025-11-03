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
   React Frontend  → KPI Dashboard + Map Playback
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
- Frontend React: displays metrics and interactive simulation  
- Deployment platform: Hugging Face Spaces (port 7860)

---
## How the Demo Works (Detailed Note on Hardcoded Variables and Constraints)

This demo runs on a fully self-contained, simulated environment for KwaZulu-Natal (KZN), South Africa.  
To ensure reproducibility and quick execution, all logistics entities, market parameters, and optimisation constraints are **hardcoded directly into the system**.  
These constants form the baseline scenario for the routing and sustainability simulation.

---

### System Operation (Summary)

1. **Message Upload and Parsing**  
   - The user uploads a CSV or Excel file containing farmer messages.  
   - The backend uses Gemini-2.0-Flash to interpret each message into structured “lots” describing crop type, quantity (kg), pickup window, and location.

2. **Optimisation Engine**  
   - The structured data is then passed into an OR-Tools routing model.  
   - Farms are automatically assigned to the nearest operational hub.  
   - Vehicles are dispatched based on available capacity, distance, and freshness constraints.  
   - The model applies hardcoded operational, time, and sustainability limits defined below.

3. **Simulation**  
   - The final plan is visualised on a Leaflet map with animated truck movements.  
   - The dashboard displays KPIs such as cost, emissions, spoilage rate, and service rate, calculated from the constants and solver results.

---

### Demo Variables and Constraints

The constants embedded in the server define the entire simulation space.  
These parameters **cannot be changed by the user in the demo** and serve as fixed optimisation constraints.

#### 1. HUBS
The available logistics hubs, their physical locations, and handling capacities:
- **Pretoria North (H1)** — latitude −25.71, longitude 28.20, capacity 1,500 kg, no cold storage.  
- **Durban South (H2)** — latitude −29.95, longitude 30.93, normal capacity 1,800 kg, cold storage 2,000 kg.  
- **Stellenbosch (H3)** — latitude −33.93, longitude 18.86, normal capacity 1,400 kg, cold storage 1,200 kg.

**Constraint:** Total inbound produce per hub cannot exceed its defined `cap_kg` or `cold_cap_kg`.  
These hubs act as dispatch centres for routing, and no new hubs are dynamically added.

---

#### 2. MARKETS
The target township markets where produce is delivered.  
Each has a fixed location, operating window, and maximum daily demand per crop:
- **Umlazi** — open 08:00–16:00  
- **KwaMashu** — open 08:00–17:00  
- **Warwick/Durban CBD** — open 08:00–17:00  
- **Pinetown** — open 09:00–17:00  

**Constraint:** Deliveries to a market cannot occur outside its `open_start`–`open_end` window.  
Each market has a capped demand (`demand[crop]`), and the solver cannot deliver more than that per crop type.

---

#### 3. FLEET
A fixed set of vehicles assigned to specific hubs.  
Each vehicle entry defines:
- `hub_id` (which hub owns it)
- `type` (insulated or non-insulated)
- `cap_kg` (maximum weight per route)
- `cost_per_km` (fuel + driver cost)
- `co2_per_km` (carbon emissions rate)
- `max_route_min` (maximum route duration in minutes)

**Constraint:**  
Each vehicle may only depart from its assigned hub and must not exceed:
- `cap_kg` → total load capacity  
- `max_route_min` → 8-hour operational time limit  
Durban South (H2) and Pretoria North (H1) are the only hubs with active vehicles in this version.

---

#### 4. FRESHNESS_MIN
Crop-specific freshness time limits (in minutes) and unit-to-kilogram conversion constants:
- Tomatoes: base life 12 hours, extended to 36 hours under cold conditions, 1 crate = 20 kg.  
- Leafy vegetables: base life 8 hours, extended to 24 hours under cold conditions, 1 crate = 12 kg or 1 bundle = 1.5 kg.  
- Potatoes: base life 72 hours, extended to 96 hours under cold conditions, 1 bag = 25 kg.

**Constraint:**  
Deliveries must occur before the crop’s freshness window expires.  
If delayed, that portion of produce is counted as “spoiled” and included in the spoilage KPI.

---

#### 5. PROFILES
Policy-driven optimisation profiles determining which objective dominates the routing solver.  
Each profile has fixed ε-constraint values:
- **low_cost:** Emission cap 1,200 kg CO₂/day, spoilage cap 8%, service rate minimum 90%.  
- **freshness_first:** Emission cap 2,000 kg CO₂/day, spoilage cap 2%, service rate minimum 95%.  
- **low_carbon:** Emission cap 800 kg CO₂/day, spoilage cap 10%, service rate minimum 85%.

**Constraint:**  
The solver must respect the caps defined by the chosen profile.  
If a solution violates a constraint (for example, spoilage exceeds S_cap_pct), it is logged as a “cap hit” and penalised in the objective function.

---

#### 6. KZN_PLACES
A built-in static mapping of township names to geographic coordinates, used when farmers specify only text-based locations.  
This mapping replaces the need for external geocoding.

**Constraint:**  
Only place names contained in `KZN_PLACES` are recognised.  
Any farmer record referencing an unlisted area is automatically excluded from the routing model.

---

#### 7. PORT and SEED
- **PORT = 7860** → required by Hugging Face Spaces runtime environment for web app hosting.  
- **VRP_SEED = 42** → sets the solver’s random seed to ensure deterministic results across runs.

**Constraint:**  
These parameters cannot be changed during execution and maintain consistent reproducibility for evaluation and peer review.

---

### Summary of Purpose
All these constants define the **spatial, temporal, and operational boundaries** of the demo.  
They make the simulation:
- Deterministic and reproducible.  
- Free from dependency on live APIs.  
- Transparent for academic auditing.  
- Scalable for future integration with real-time data sources.

In essence, the hardcoded constraints create a **controlled digital twin** of the KwaZulu-Natal agricultural logistics network — ensuring that every demonstration run yields explainable, consistent, and comparable results.
## Citation
If you reference this demo or its research output, please cite:
> Zhou-Mukamuri, et al. (2025). *Artificial Intelligence-Driven Sustainable Logistics for Informal Agricultural Markets in Southern Africa*. Quantilytix Research Lab.

---

## License
MIT License © 2025 Quantilytix / Zhou–Mukamuri Research Team
