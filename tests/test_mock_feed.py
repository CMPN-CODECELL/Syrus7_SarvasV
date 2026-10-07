from fastapi.testclient import TestClient

from backend.market_data.mock_feed import create_mock_feed_app


def test_mock_feed_health_and_defaults():
    app = create_mock_feed_app()
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "algoshield-mock-market-data"
    assert data["status"] == "UP"
    assert data["ticks_count"] == 0


def test_mock_feed_single_tick_and_query():
    app = create_mock_feed_app()
    client = TestClient(app)

    payload = {
        "symbol": "TATA",
        "price": "500.50",
        "quantity": 10,
        "event_timestamp": 1000,
        "event_id": "ev-1",
    }
    res = client.post("/ticks", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["tick"]["symbol"] == "TATA"
    assert data["tick"]["price"] == "500.50"
    assert data["tick"]["quantity"] == 10
    assert data["tick"]["event_id"] == "ev-1"

    # Query ticks
    query_res = client.get("/ticks?symbol=TATA")
    assert query_res.status_code == 200
    ticks = query_res.json()
    assert len(ticks) == 1
    assert ticks[0]["symbol"] == "TATA"


def test_mock_feed_batch_ticks_and_candle_aggregation():
    app = create_mock_feed_app()
    client = TestClient(app)

    # Ingest ticks across 60-second boundaries
    batch = [
        {
            "symbol": "INFY",
            "price": "1500",
            "quantity": 5,
            "event_timestamp": 0,
            "event_id": "i1",
        },
        {
            "symbol": "INFY",
            "price": "1510",
            "quantity": 10,
            "event_timestamp": 30,
            "event_id": "i2",
        },
        {
            "symbol": "INFY",
            "price": "1490",
            "quantity": 2,
            "event_timestamp": 60,
            "event_id": "i3",
        },
    ]
    res = client.post("/ticks/batch", json=batch)
    assert res.status_code == 201
    data = res.json()
    assert data["count"] == 3
    # Tick at ts=60 should have closed the 1m candle [0, 60)
    assert len(data["closed_candles"]) >= 1
    c1m = [c for c in data["closed_candles"] if c["interval"] == 60][0]
    assert c1m["symbol"] == "INFY"
    assert c1m["open"] == "1500"
    assert c1m["high"] == "1510"
    assert c1m["low"] == "1500"
    assert c1m["close"] == "1510"
    assert c1m["volume"] == 15

    # Query candles endpoint
    candles_res = client.get("/candles?symbol=INFY&interval=60")
    assert candles_res.status_code == 200
    assert len(candles_res.json()) >= 1


def test_mock_feed_replay_demo():
    app = create_mock_feed_app()
    client = TestClient(app)

    res = client.post("/replay/demo?start=1700000100")
    assert res.status_code == 200
    assert res.json()["loaded_ticks"] == 33

    health_res = client.get("/health")
    assert health_res.json()["ticks_count"] == 33
    assert health_res.json()["candles_count"] > 0


def test_mock_feed_stream_ticks():
    app = create_mock_feed_app()
    client = TestClient(app)

    # Post a tick
    client.post("/ticks", json={"symbol": "NIFTY", "price": "22000", "quantity": 50})

    # Stream
    res = client.get("/stream/ticks?limit=5")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    assert "data: " in res.text
    assert "NIFTY" in res.text
    assert "ping" in res.text


def test_mock_feed_validation():
    app = create_mock_feed_app()
    client = TestClient(app)

    # Negative price rejected
    bad_price = client.post("/ticks", json={"symbol": "NIFTY", "price": "-10"})
    assert bad_price.status_code == 422

    # Zero price rejected
    zero_price = client.post("/ticks", json={"symbol": "NIFTY", "price": "0"})
    assert zero_price.status_code == 422

    # Empty symbol rejected
    empty_sym = client.post("/ticks", json={"symbol": "   ", "price": "100"})
    assert empty_sym.status_code == 422
