import os
import requests
from flask import Flask, jsonify

app = Flask(__name__)
API_URL = "https://api.realmarketapi.com/api/v1/candle"
API_KEY = os.environ.get("REALMARKETAPI_KEY", "").strip()
TIMEFRAMES = ("M1", "M5", "M15")

def extract_candles(payload):
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = next((payload[k] for k in ("candles", "data", "items", "results", "CandleData")
                     if isinstance(payload.get(k), list)), None)
        if rows is None and all(k in payload for k in ("OpenPrice", "HighPrice", "LowPrice", "ClosePrice")):
            rows = [payload]
        if rows is None:
            raise ValueError("Unrecognised candle response shape")
    else:
        raise ValueError("Unexpected provider response")
    result = []
    for row in rows:
        try:
            def val(*keys):
                for key in keys:
                    if row.get(key) is not None:
                        return float(row[key])
                raise ValueError("Missing OHLC value")
            result.append({
                "open": val("open", "Open", "OpenPrice", "openPrice"),
                "high": val("high", "High", "HighPrice", "highPrice"),
                "low": val("low", "Low", "LowPrice", "lowPrice"),
                "close": val("close", "Close", "ClosePrice", "closePrice")
            })
        except (ValueError, TypeError, AttributeError):
            continue
    if not result:
        raise ValueError("No usable OHLC candles returned")
    return result

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.get("/")
def index():
    return jsonify({"service": "GOLD SNIPER AI data bridge", "endpoints": ["/health", "/candles"]})

@app.get("/health")
def health():
    return jsonify({"status": "ok", "provider_key_configured": bool(API_KEY)})

@app.route("/candles", methods=["GET", "OPTIONS"])
def candles():
    if not API_KEY:
        return jsonify({"error": "Server API key is not configured"}), 503
    if __import__("flask").request.method == "OPTIONS":
        return ("", 204)
    result = {}
    try:
        for timeframe in TIMEFRAMES:
            response = requests.get(API_URL, params={
                "apiKey": API_KEY, "symbolCode": "XAUUSD", "timeFrame": timeframe
            }, timeout=15)
            if response.status_code != 200:
                return jsonify({"error": "Provider request failed", "timeframe": timeframe,
                                "provider_status": response.status_code}), 502
            result[timeframe] = extract_candles(response.json())
        return jsonify(result)
    except requests.RequestException:
        return jsonify({"error": "Could not reach market data provider"}), 502
    except (ValueError, TypeError) as exc:
        return jsonify({"error": "Could not interpret provider candle data", "detail": str(exc)}), 502
