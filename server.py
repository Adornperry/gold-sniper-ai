import os
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

API_URL = "https://api.realmarketapi.com/api/v1/candle"
API_KEY = os.environ.get("REALMARKETAPI_KEY", "").strip()
TIMEFRAMES = ("M1", "M5", "H1")


def extract_candles(payload):
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for key in ("Data", "data", "candles", "Candles", "items", "results"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        if rows is None and all(k in payload for k in
                                ("OpenPrice", "HighPrice", "LowPrice", "ClosePrice")):
            rows = [payload]
        if rows is None:
            raise ValueError("Provider response did not contain a candle array")
    else:
        raise ValueError("Unexpected provider response format")

    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        def val(*keys):
            for key in keys:
                value = row.get(key)
                if value is not None:
                    return float(value)
            raise ValueError("Missing OHLC field")

        try:
            result.append({
                "open": val("open", "Open", "OpenPrice", "openPrice"),
                "high": val("high", "High", "HighPrice", "highPrice"),
                "low": val("low", "Low", "LowPrice", "lowPrice"),
                "close": val("close", "Close", "ClosePrice", "closePrice"),
            })
        except (ValueError, TypeError):
            continue

    if not result:
        raise ValueError("No usable OHLC candles returned")
    # Provider documents /candle as most-recent-first; analysis needs oldest-first.
    result.reverse()
    return result


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.get("/")
def index():
    return jsonify({
        "service": "GOLD SNIPER AI data bridge",
        "endpoints": ["/health", "/candles"]
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "provider_key_configured": bool(API_KEY)
    })


@app.route("/candles", methods=["GET", "OPTIONS"])
def candles():
    if request.method == "OPTIONS":
        return ("", 204)
    if not API_KEY:
        return jsonify({"error": "Server API key is not configured"}), 503

    result = {}
    try:
        for timeframe in TIMEFRAMES:
            response = requests.get(
                API_URL,
                params={
                    "apiKey": API_KEY,
                    "symbolCode": "XAUUSD",
                    "timeFrame": timeframe,
                },
                timeout=20,
            )
            if response.status_code != 200:
                return jsonify({
                    "error": "Market data provider request failed",
                    "timeframe": timeframe,
                    "provider_status": response.status_code,
                }), 502
            result[timeframe] = extract_candles(response.json())

        return jsonify(result)
    except requests.RequestException:
        return jsonify({"error": "Could not reach market data provider"}), 502
    except (ValueError, TypeError) as exc:
        return jsonify({
            "error": "Could not interpret provider candle data",
            "detail": str(exc),
        }), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
