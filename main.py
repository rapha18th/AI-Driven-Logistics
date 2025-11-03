import os
import io
import re
import sys
import math
import json
import time
import logging
import traceback
import datetime as dt
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS

# LLM
import google.generativeai as genai  # target 0.4.1 semantics

# OR-Tools
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Config / Env
# -----------------------------------------------------------------------------
PORT = int(os.environ.get("PORT", "7860"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("Gemini") or ""
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
MODEL_FALLBACK = os.environ.get("GEMINI_MODEL_FALLBACK", "gemini-1.5-flash")
RANDOM_SEED = int(os.environ.get("VRP_SEED", "42"))
np.random.seed(RANDOM_SEED)

# -----------------------------------------------------------------------------
# Flask
# -----------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# -----------------------------------------------------------------------------
# Static demo config (KZN)
# -----------------------------------------------------------------------------
HUBS = [
    {"id": "H1", "name": "Pretoria North", "lat": -25.71, "lon": 28.20, "cap_kg": 1500, "cold_cap_kg": 0},
    {"id": "H2", "name": "Durban South",   "lat": -29.95, "lon": 30.93, "cap_kg": 1800, "cold_cap_kg": 2000},
    {"id": "H3", "name": "Stellenbosch",   "lat": -33.93, "lon": 18.86, "cap_kg": 1400, "cold_cap_kg": 1200},
]

MARKETS = [
    {"id":"M_Umlazi","name":"Umlazi","lat":-29.970,"lon":30.878,"open_start":8*60,"open_end":16*60,"demand":{"tomatoes":350,"leafy":250,"potatoes":250}},
    {"id":"M_KwaMashu","name":"KwaMashu","lat":-29.763,"lon":30.963,"open_start":8*60,"open_end":17*60,"demand":{"tomatoes":300,"leafy":200,"potatoes":180}},
    {"id":"M_Warwick","name":"Warwick/Durban CBD","lat":-29.857,"lon":31.021,"open_start":8*60,"open_end":17*60,"demand":{"tomatoes":400,"leafy":300,"potatoes":300}},
    {"id":"M_Pinetown","name":"Pinetown","lat":-29.817,"lon":30.887,"open_start":9*60,"open_end":17*60,"demand":{"tomatoes":250,"leafy":150,"potatoes":220}},
]

FLEET = [
    {"id":"V1","hub_id":"H2","type":"insulated","cap_kg":1400,"cost_per_km":13.5,"co2_per_km":1.1,"max_route_min":8*60},
    {"id":"V2","hub_id":"H2","type":"non_insulated","cap_kg":1200,"cost_per_km":12.0,"co2_per_km":1.2,"max_route_min":8*60},
]

FRESHNESS_MIN = {
    "tomatoes": {"base": 12*60, "with_cold": 36*60, "crate_to_kg": 20},
    "leafy":    {"base": 8*60,  "with_cold": 24*60, "crate_to_kg": 12, "bundle_to_kg": 1.5},
    "potatoes": {"base": 72*60, "with_cold": 96*60, "bag_to_kg": 25},
}

PROFILES = {
    "low_cost":        {"E_cap": 1200.0, "S_cap_pct": 8.0,  "R_min_pct": 90.0},
    "freshness_first": {"E_cap": 2000.0, "S_cap_pct": 2.0,  "R_min_pct": 95.0},
    "low_carbon":      {"E_cap": 800.0,  "S_cap_pct": 10.0, "R_min_pct": 85.0},
}

KZN_PLACES = {
    "umlazi": (-29.970, 30.878),
    "kwamashu": (-29.763, 30.963),
    "warwick": (-29.857, 31.021),
    "durban cbd": (-29.858, 31.021),
    "pinetown": (-29.817, 30.887),
    "phoenix": (-29.707, 31.034),
    "isipingo": (-29.994, 30.955),
    "verulam": (-29.683, 31.055),
    "tongaat": (-29.583, 31.116),
    "richards bay": (-28.780, 32.057),
}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def flat_km(a, b):
    lat_km = (a["lat"] - b["lat"]) * 111.0
    lon_km = (a["lon"] - b["lon"]) * 111.0 * math.cos(math.radians((a["lat"] + b["lat"])/2.0))
    return max(0.05, math.hypot(lat_km, lon_km))

def travel_min(km, rainy=False):
    speed_kmh = 50.0
    return (km / speed_kmh) * 60.0 * (1.25 if rainy else 1.0)

def parse_time_minutes(ts: Optional[str]) -> Optional[int]:
    if not ts: return None
    try:
        dtm = dt.datetime.fromisoformat(ts.replace("Z",""))
        return dtm.hour*60 + dtm.minute
    except Exception:
        return None

def unit_to_kg(crop: str, val: Optional[float], unit: str) -> Optional[float]:
    if val is None: return None
    unit = (unit or "").lower()
    c = (crop or "").lower()
    if unit in ["kg","kilograms","kilos"]:
        return float(val)
    if c.startswith("tom"):
        if "crate" in unit: return float(val) * FRESHNESS_MIN["tomatoes"]["crate_to_kg"]
    if c.startswith("leaf"):
        if "bundle" in unit: return float(val) * FRESHNESS_MIN["leafy"].get("bundle_to_kg",1.5)
        if "crate" in unit:  return float(val) * FRESHNESS_MIN["leafy"].get("crate_to_kg",12)
    if c.startswith("pot"):
        if "bag" in unit:    return float(val) * FRESHNESS_MIN["potatoes"]["bag_to_kg"]
    return float(val)

def assign_to_hubs(farms: List[Dict[str,Any]], hubs: List[Dict[str,Any]]) -> Dict[str,str]:
    rem = {h["id"]: h["cap_kg"] for h in hubs}
    mapping = {}
    for f in farms:
        ordered = sorted(hubs, key=lambda h: flat_km(f, h))
        for h in ordered:
            if rem[h["id"]] >= f["kg"]:
                mapping[f["id"]] = h["id"]
                rem[h["id"]] -= f["kg"]
                break
        if f["id"] not in mapping:
            mapping[f["id"]] = ordered[0]["id"]
            rem[ordered[0]["id"]] -= f["kg"]
    return mapping

# -----------------------------------------------------------------------------
# Gemini wiring (0.4.1 style) with fallback + probe
# -----------------------------------------------------------------------------
EXTRACTION_PROMPT = """Extract structured logistics 'lots' from each noisy farmer message.
Return ONLY strict JSON (no markdown) as an array, one object per input message, with this schema:

{
  "message_id": string,
  "actor_type": "farmer",
  "phone": string|null,
  "location_text": string|null,
  "geo": {"lat": number|null, "lon": number|null, "quality": "pin"|"matched"|"approx"|"unknown"},
  "crop_items": [{"crop": "tomatoes"|"leafy"|"potatoes", "quantity_value": number|null, "quantity_unit": "kg"|"crates"|"bags"|"bundles"|null, "kg_estimate": number|null}],
  "availability_window": {"start_local": string|null, "end_local": string|null, "tz": "Africa/Johannesburg"},
  "intent": "offer"|"update"|"cancel"|"unknown",
  "notes": string|null,
  "confidence": {"geo": number, "time": number, "quantities": number}
}

Rules:
- If units are crates/bags/bundles, compute kg_estimate using: tomatoes 1 crate≈20kg; potatoes 1 bag≈25kg; leafy 1 bundle≈1.5kg (or 1 crate≈12kg).
- Parse vague times relative to the provided timestamp_local (Africa/Johannesburg).
- If coordinates present, geo.quality="pin".
- If known KZN place (Umlazi, KwaMashu, Warwick, Durban CBD, Pinetown, Phoenix, Isipingo, Verulam, Tongaat, Richards Bay), set lat/lon and geo.quality="matched".
- If ambiguous, lat/lon null and geo.quality="unknown".
- Return ONLY a JSON array. No commentary.
"""

def configure_gemini_model() -> genai.GenerativeModel:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY (or Gemini) not set")
    genai.configure(api_key=GEMINI_API_KEY)
    model_name = GEMINI_MODEL
    try:
        logger.info(f"[Gemini] Using model: {model_name}")
        return genai.GenerativeModel(model_name)
    except Exception as e:
        logger.warning(f"[Gemini] Failed to init model '{model_name}': {e}. Trying fallback '{MODEL_FALLBACK}'")
        return genai.GenerativeModel(MODEL_FALLBACK)

def extract_json_from_response(response_text: str) -> Any:
    if not response_text:
        raise ValueError("Empty LLM response")
    m = re.search(r"```json\s*($begin:math:display$[\\s\\S]*?$end:math:display$|\{[\s\S]*?\})\s*```", response_text, re.IGNORECASE)
    if m:
        return json.loads(m.group(1).strip())
    m = re.search(r"\[[\s\S]*\]", response_text)
    if m:
        return json.loads(m.group(0))
    m = re.search(r"\{[\s\S]*\}", response_text)
    if m:
        return json.loads(m.group(0))
    raise ValueError("No valid JSON found in LLM response")

def repair_json_with_gemini(model: genai.GenerativeModel, broken: str) -> str:
    repair_prompt = (
        "The following text is JSON that is syntactically incorrect. "
        "Fix it so it becomes valid JSON. Return ONLY the corrected raw JSON, no markdown.\n\n"
        f"{broken}"
    )
    resp = model.generate_content(repair_prompt)
    return getattr(resp, "text", "") or "[]"

def call_gemini_with_retry_extract(model: genai.GenerativeModel, user_payload: str,
                                   retries=3, backoff_factor=2) -> Any:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            t0 = time.time()
            resp = model.generate_content([EXTRACTION_PROMPT, user_payload])
            dt_ms = int((time.time() - t0) * 1000)
            text = getattr(resp, "text", "") or ""
            logger.info(f"[Gemini] batch call ok in {dt_ms} ms; len(resp.text)={len(text)}")
            try:
                return extract_json_from_response(text)
            except Exception:
                logger.warning("[Gemini] JSON parse failed; attempting repair")
                repaired = repair_json_with_gemini(model, text)
                return extract_json_from_response(repaired)
        except Exception as e:
            last_err = e
            msg = str(e)
            logger.error(f"[Gemini] call failed (attempt {attempt}/{retries}): {msg}")
            if ("429" in msg or "RateLimit" in msg) and attempt < retries:
                wait = backoff_factor ** attempt
                logger.warning(f"[Gemini] rate-limited; sleeping {wait}s")
                time.sleep(wait)
            else:
                break
    raise RuntimeError(f"Gemini extraction failed after retries: {last_err}")

def _geocode_known_kzn_places(text: str) -> Optional[Dict[str,float]]:
    t = (text or "").lower()
    for k, (lat, lon) in KZN_PLACES.items():
        if k in t:
            return {"lat": lat, "lon": lon, "quality": "matched"}
    return None

def _safe_float(v):
    try:
        if v is None or v == "": return None
        return float(v)
    except:
        return None

def _postprocess_llm_lots(raw_lots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for lot in raw_lots:
        geo = lot.get("geo") or {}
        if (not geo.get("lat")) or (not geo.get("lon")):
            m = _geocode_known_kzn_places(lot.get("location_text",""))
            if m:
                lot["geo"] = m
            else:
                lot["geo"] = {"lat": None, "lon": None, "quality": "unknown"}

        items = lot.get("crop_items") or []
        norm_items = []
        for it in items:
            crop = (it.get("crop","") or "").lower().strip()
            if crop.startswith("tom"): crop = "tomatoes"
            elif crop.startswith("leaf"): crop = "leafy"
            elif crop.startswith("pot"): crop = "potatoes"
            norm_items.append({
                "crop": crop,
                "quantity_value": _safe_float(it.get("quantity_value")),
                "quantity_unit": it.get("quantity_unit") or None,
                "kg_estimate": _safe_float(it.get("kg_estimate")),
            })
        lot["crop_items"] = norm_items
        out.append(lot)
    return out

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/health")
def health():
    return jsonify({
        "status":"ok",
        "time":dt.datetime.utcnow().isoformat()+"Z",
        "model":GEMINI_MODEL,
        "has_key": bool(GEMINI_API_KEY)
    })

@app.route("/profiles")
def profiles():
    return jsonify(PROFILES)

@app.route("/ingest", methods=["POST"])
def ingest():
    try:
        if "file" not in request.files:
            return jsonify({"error":"no file uploaded"}), 400
        f = request.files["file"]
        name = (f.filename or "").lower()
        logger.info(f"[ingest] filename={name}")
        data = f.read()
        logger.info(f"[ingest] file bytes={len(data)}")
        try:
            if name.endswith(".xlsx") or name.endswith(".xls"):
                df = pd.read_excel(io.BytesIO(data))
            else:
                df = pd.read_csv(io.BytesIO(data))
        except Exception as e:
            logger.error(f"[ingest] pandas read error: {e}")
            return jsonify({"error": f"failed to read file: {e}"}), 400

        logger.info(f"[ingest] df shape={df.shape}; cols={list(df.columns)}")
        required = ["message_id","sender_phone","timestamp_local","message_text"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            logger.error(f"[ingest] missing columns: {missing}")
            return jsonify({"error": f"missing required columns: {missing}"}), 400

        return jsonify({
            "rows": df.head(50).to_dict(orient="records"),
            "total": int(len(df))
        })
    except Exception:
        logger.error("[ingest] server error:\n%s", traceback.format_exc())
        return jsonify({"error":"Internal server error"}), 500

@app.route("/extract", methods=["POST"])
def extract():
    try:
        if not GEMINI_API_KEY:
            logger.error("[extract] missing GEMINI_API_KEY")
            return jsonify({"error":"GEMINI_API_KEY (or Gemini) not set"}), 500

        if "file" not in request.files:
            return jsonify({"error":"no file uploaded"}), 400
        f = request.files["file"]
        name = (f.filename or "").lower()
        logger.info(f"[extract] filename={name}")
        data = f.read()
        logger.info(f"[extract] file bytes={len(data)}")
        try:
            if name.endswith(".xlsx") or name.endswith(".xls"):
                df = pd.read_excel(io.BytesIO(data))
            else:
                df = pd.read_csv(io.BytesIO(data))
        except Exception as e:
            logger.error(f"[extract] pandas read error: {e}")
            return jsonify({"error": f"failed to read file: {e}"}), 400

        logger.info(f"[extract] df shape={df.shape}; cols={list(df.columns)}")
        required = ["message_id","sender_phone","timestamp_local","message_text"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            logger.error(f"[extract] missing columns: {missing}")
            return jsonify({"error": f"missing required columns: {missing}"}), 400

        # Configure Gemini model (with fallback)
        try:
            model = configure_gemini_model()
        except Exception as e:
            logger.error(f"[extract] configure_gemini_model failed: {e}")
            return jsonify({"error": f"gemini_init_failed: {e}"}), 502

        rows = df.to_dict(orient="records")
        lots: List[Dict[str, Any]] = []
        BATCH = 30
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i+BATCH]
            user_payload = json.dumps({
                "messages":[
                    {
                        "message_id": str(r.get("message_id")),
                        "phone": str(r.get("sender_phone","")),
                        "timestamp_local": str(r.get("timestamp_local","")),
                        "message_text": str(r.get("message_text","")).strip()
                    } for r in batch
                ]
            }, ensure_ascii=False)

            logger.info(f"[extract] batch {i//BATCH+1}: size={len(batch)}, payload_len={len(user_payload)}")

            try:
                parsed = call_gemini_with_retry_extract(model, user_payload, retries=3)
                # debug preview
                try:
                    preview = json.dumps(parsed)[:300]
                    logger.debug(f"[extract] batch parsed preview: {preview}")
                except Exception:
                    pass

                if isinstance(parsed, dict) and "results" in parsed:
                    parsed = parsed["results"]
                if not isinstance(parsed, list):
                    parsed = [parsed]
                parsed = _postprocess_llm_lots(parsed)
                lots.extend(parsed)
            except Exception as e:
                logger.error(f"[extract] LLM failure on batch; will emit placeholders: {e}")
                logger.debug("[extract] LLM traceback:\n%s", traceback.format_exc())
                for r in batch:
                    lots.append({
                        "message_id": str(r.get("message_id")),
                        "actor_type": "farmer",
                        "phone": str(r.get("sender_phone","")),
                        "location_text": None,
                        "geo": {"lat": None, "lon": None, "quality":"unknown"},
                        "crop_items": [],
                        "availability_window": {"start_local": None, "end_local": None, "tz":"Africa/Johannesburg"},
                        "intent": "unknown",
                        "notes": f"extraction_error: {e}",
                        "confidence": {"geo":0.0,"time":0.0,"quantities":0.0}
                    })

        logger.info(f"[extract] done. lots_count={len(lots)}")
        return jsonify({"lots": lots, "count": len(lots)})
    except Exception:
        logger.error("[extract] server error:\n%s", traceback.format_exc())
        return jsonify({"error": "Internal server error"}), 500

@app.route("/plan", methods=["POST"])
def plan():
    try:
        payload = request.get_json(force=True) or {}
        profile_key = payload.get("profile","freshness_first")
        rainy = bool(payload.get("rainy", False))
        lots = payload.get("lots") or []

        logger.info(f"[plan] profile={profile_key} rainy={rainy} lots_count={len(lots)}")

        profile = PROFILES.get(profile_key)
        if not profile:
            return jsonify({"error":"invalid profile"}), 400

        farm_nodes = []
        for lot in lots:
            geo = lot.get("geo") or {}
            lat, lon = geo.get("lat"), geo.get("lon")
            if lat is None or lon is None:
                continue
            total_kg = 0.0
            for item in (lot.get("crop_items") or []):
                kg = item.get("kg_estimate")
                if kg is None:
                    cv = item.get("quantity_value")
                    unit = (item.get("quantity_unit") or "").lower()
                    crop = item.get("crop") or ""
                    kg = unit_to_kg(crop, cv, unit)
                total_kg += float(kg or 0.0)
            if total_kg <= 0:
                continue
            av = lot.get("availability_window") or {}
            s = parse_time_minutes(av.get("start_local")) or 6*60
            e = parse_time_minutes(av.get("end_local")) or 12*60
            farm_nodes.append({
                "id": f"F_{lot.get('message_id')}",
                "lat": float(lat), "lon": float(lon),
                "kg": total_kg,
                "window": (int(s), int(e)),
                "raw": lot
            })

        logger.info(f"[plan] farm_nodes={len(farm_nodes)}")

        assignment = assign_to_hubs(farm_nodes, HUBS)
        results_by_hub = []
        totals = {"cost":0.0,"co2":0.0,"km":0.0,"delivered":0.0,"fresh_viol":0.0}
        total_demand = sum(sum(m["demand"].values()) for m in MARKETS)

        for hub in HUBS:
            lots_h = [f for f in farm_nodes if assignment.get(f["id"]) == hub["id"]]
            if not lots_h:
                continue
            supply_kg = sum(f["kg"] for f in lots_h)
            if supply_kg <= 0: 
                continue
            logger.info(f"[plan] solving hub={hub['id']} supply_kg={round(supply_kg,1)}")
            res = solve_hub_to_markets(hub, FLEET, MARKETS, supply_kg, rainy=rainy)
            results_by_hub.append(res)
            totals["cost"] += res["cost_zar"]
            totals["co2"] += res["emissions_kg"]
            totals["km"] += res["distance_km"]
            totals["delivered"] += res["delivered_kg"]
            totals["fresh_viol"] += res["freshness_violations_kg"]

        service_rate = 100.0 * totals["delivered"] / max(1e-6, total_demand)
        spoilage_pct = 100.0 * totals["fresh_viol"] / max(1e-6, totals["delivered"])

        cap_hits = []
        if totals["co2"] > profile["E_cap"]: cap_hits.append("emissions_cap")
        if spoilage_pct > profile["S_cap_pct"]: cap_hits.append("spoilage_cap")
        if service_rate < profile["R_min_pct"]: cap_hits.append("service_min")

        brief = []
        if rainy: brief.append("Rainy-day travel time factor applied (×1.25).")
        if "spoilage_cap" in cap_hits: brief.append("Spoilage cap binding: cold-chain saturation or late arrivals; insulated vehicle or earlier windows advised.")
        if "emissions_cap" in cap_hits: brief.append("Emission cap binding: consolidate legs or prioritize short-haul markets.")
        if "service_min" in cap_hits: brief.append("Service minimum not met: add capacity or relax windows.")
        if not cap_hits: brief.append("All ε-constraints satisfied under selected profile.")

        resp = {
            "profile": profile_key,
            "kpis": {
                "total_cost_zar": round(totals["cost"],2),
                "total_emissions_kg": round(totals["co2"],2),
                "total_distance_km": round(totals["km"],2),
                "delivered_kg": round(totals["delivered"],1),
                "service_rate_pct": round(service_rate,1),
                "spoilage_pct_proxy": round(spoilage_pct,1),
            },
            "epsilon_caps": {**profile, "cap_hits": cap_hits},
            "decision_brief": brief,
            "hub_assignment": assignment,
            "results_by_hub": results_by_hub
        }
        logger.info(f"[plan] done. km={resp['kpis']['total_distance_km']} cost={resp['kpis']['total_cost_zar']} delivered={resp['kpis']['delivered_kg']}")
        return jsonify(resp)
    except Exception:
        logger.error("[plan] server error:\n%s", traceback.format_exc())
        return jsonify({"error":"Internal server error"}), 500

# -----------------------------------------------------------------------------
# OR-Tools VRP (hub -> markets)
# -----------------------------------------------------------------------------
def solve_hub_to_markets(hub, fleet, markets, supply_kg, rainy=False):
    nodes = [hub] + markets
    n = len(nodes)
    vehs = [v for v in fleet if v["hub_id"] == hub["id"]]
    if not vehs:
        return _empty_hub_result(hub["id"], note="No vehicles at this hub")

    # Distances & times
    dist_km = np.zeros((n, n))
    time_min = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            d = flat_km(nodes[i], nodes[j])
            dist_km[i, j] = d
            time_min[i, j] = travel_min(d, rainy=rainy)

    # Demand scaling (simple proportional split)
    dem = [0.0] + [sum(m["demand"].values()) for m in markets]
    total_dem = sum(dem)
    if total_dem <= 0:
        return _empty_hub_result(hub["id"], note="No market demand")
    ratio = min(1.0, supply_kg / total_dem)
    demand_deliver = [0.0] + [x * ratio for x in dem[1:]]

    # OR-Tools model
    manager = pywrapcp.RoutingIndexManager(n, len(vehs), 0)
    routing = pywrapcp.RoutingModel(manager)

    # Transit callback = travel time (minutes)
    def time_cb(from_idx, to_idx):
        i = manager.IndexToNode(from_idx)
        j = manager.IndexToNode(to_idx)
        return int(time_min[i, j])

    transit_idx = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # ---- FIX: large horizon + per-vehicle route-duration cap via dimension span ----
    HORIZON = 24 * 60  # full day
    routing.AddDimension(
        transit_idx,
        30,          # waiting/slack allowance
        HORIZON,     # big horizon so market windows up to 17:00 are feasible
        False,       # don't force start at zero
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")

    # Depot (hub) windows for ALL vehicles
    for v_id in range(len(vehs)):
        time_dim.CumulVar(routing.Start(v_id)).SetRange(0, HORIZON)
        time_dim.CumulVar(routing.End(v_id)).SetRange(0, HORIZON)

    # Market time windows (e.g., 08:00–17:00)
    for node in range(1, n):
        s = markets[node - 1]["open_start"]
        e = markets[node - 1]["open_end"]
        time_dim.CumulVar(manager.NodeToIndex(node)).SetRange(int(s), int(e))

    # Cap each vehicle's working time using the dimension's span bound (CORRECT API)
    max_route = int(max(v["max_route_min"] for v in vehs))
    for v_id in range(len(vehs)):
        time_dim.SetSpanUpperBoundForVehicle(max_route, v_id)

    # Capacity (kg)
    def demand_cb(from_idx):
        i = manager.IndexToNode(from_idx)
        return int(demand_deliver[i])

    dem_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(
        dem_idx,
        0,
        [int(v["cap_kg"]) for v in vehs],
        True,
        "Capacity",
    )

    # Search params
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(10)
    params.log_search = False

    # Extra debug to diagnose feasibility quickly
    try:
        tws = [(m["open_start"], m["open_end"]) for m in markets]
        logging.debug(f"[vrp] HORIZON={HORIZON}, max_route={max_route}, windows={tws}")
    except Exception:
        pass

    sol = routing.SolveWithParameters(params)
    if not sol:
        return _empty_hub_result(
            hub["id"],
            note=f"No solution in time limit (HORIZON={HORIZON}, max_route={max_route})."
        )

    # Build routes & KPIs
    total_km = 0.0
    total_cost = 0.0
    total_em = 0.0
    delivered = 0.0
    freshness_viol = 0.0
    routes = []

    for v_id, veh in enumerate(vehs):
        idx = routing.Start(v_id)
        rnodes = []
        route_km = 0.0
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            tmin = sol.Value(time_dim.CumulVar(idx))
            rnodes.append((node, tmin))
            next_idx = sol.Value(routing.NextVar(idx))
            if not routing.IsEnd(next_idx):
                nxt = manager.IndexToNode(next_idx)
                route_km += dist_km[node, nxt]
            idx = next_idx
        rnodes.append((manager.IndexToNode(idx), sol.Value(time_dim.CumulVar(idx))))

        route_cost = route_km * veh["cost_per_km"]
        route_em = route_km * veh["co2_per_km"]
        total_km += route_km
        total_cost += route_cost
        total_em += route_em

        insulated = (veh["type"] == "insulated")
        for node, arriv in rnodes:
            if node == 0:
                continue
            mk = markets[node - 1]
            qty = demand_deliver[node]
            delivered += qty
            totm = sum(mk["demand"].values()) + 1e-6
            viol_share = 0.0
            for crop, demc in mk["demand"].items():
                share = demc / totm
                thr = FRESHNESS_MIN[crop]["with_cold"] if insulated else FRESHNESS_MIN[crop]["base"]
                if arriv > thr:
                    viol_share += share
            freshness_viol += qty * viol_share

        pretty = []
        for node, arriv in rnodes:
            if node == 0:
                pretty.append({"type": "hub", "id": hub["id"], "name": hub["name"], "arrive_min": int(arriv)})
            else:
                mk = markets[node - 1]
                pretty.append({
                    "type": "market",
                    "id": mk["id"],
                    "name": mk["name"],
                    "arrive_min": int(arriv),
                    "deliver_kg": round(demand_deliver[node], 1)
                })

        routes.append({
            "vehicle_id": veh["id"],
            "insulated": insulated,
            "distance_km": round(route_km, 2),
            "emissions_kg": round(route_em, 2),
            "cost_zar": round(route_cost, 2),
            "stops": pretty
        })

    return {
        "hub_id": hub["id"],
        "routes": routes,
        "delivered_kg": round(delivered, 1),
        "distance_km": round(total_km, 2),
        "emissions_kg": round(total_em, 2),
        "cost_zar": round(total_cost, 2),
        "freshness_violations_kg": round(freshness_viol, 1),
        "notes": []
    }

def _empty_hub_result(hub_id, note=""):
    return {
        "hub_id": hub_id,
        "routes": [],
        "delivered_kg": 0.0,
        "distance_km": 0.0,
        "emissions_kg": 0.0,
        "cost_zar": 0.0,
        "freshness_violations_kg": 0.0,
        "notes": [note] if note else []
    }

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # configure early to catch key issues in logs
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            logger.info("[boot] Gemini configured. model=%s", GEMINI_MODEL)
        except Exception as e:
            logger.warning("[boot] Gemini configure failed: %s", e)
    else:
        logger.warning("[boot] GEMINI_API_KEY not set")

    logger.info(f"[boot] starting Flask on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
