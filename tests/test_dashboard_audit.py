from dashboard.audit import (
    format_artifact_rows,
    format_blocked_trade_rows,
    format_latest_artifact_summary,
    format_run_detail,
    format_run_history_rows,
    format_signal_rows,
    format_trade_rows,
)


def test_format_signal_rows_surfaces_indicator_fields():
    rows = [
        {
            "ts": "2026-03-31T00:00:00Z",
            "symbol": "BTC/USD",
            "action": "BUY",
            "reason": "EMA_BULLISH_BREAKOUT",
            "indicator_json": '{"price": 69420, "ema20": 68000, "ema50": 66000, "recent_high": 69000, "recent_low": 65000}',
            "should_execute": 1,
        }
    ]

    formatted = format_signal_rows(rows)

    assert formatted[0]["symbol"] == "BTC/USD"
    assert formatted[0]["should_execute"] is True
    assert formatted[0]["ema20"] == 68000


def test_format_blocked_trade_rows_surfaces_risk_reasons():
    rows = [
        {
            "ts": "2026-03-31T00:00:00Z",
            "symbol": "SOL/USD",
            "side": "SELL",
            "attempted_quantity": 0.0,
            "attempted_price": 149.25,
            "block_reason": "INVALID_QUANTITY, NO_OPEN_POSITION",
            "context_json": '{"signal_reason": "EMA_BEARISH_BREAKDOWN", "risk_reason_codes": ["INVALID_QUANTITY", "NO_OPEN_POSITION"]}',
        }
    ]

    formatted = format_blocked_trade_rows(rows)

    assert formatted[0]["signal_reason"] == "EMA_BEARISH_BREAKDOWN"
    assert "NO_OPEN_POSITION" in formatted[0]["risk_reason_codes"]


def test_run_history_and_detail_extract_summary_fields():
    rows = [
        {
            "id": "12345678-abcd",
            "ts": "2026-03-31T00:00:00Z",
            "status": "COMPLETED",
            "summary_json": '{"signal_count": 3, "executed_count": 2, "blocked_count": 1, "artifact_count": 2, "latest_prices": {"BTC/USD": 69420}, "metrics": {"ending_cash": 80000}}',
        }
    ]

    history = format_run_history_rows(rows)
    detail = format_run_detail(history[0])

    assert history[0]["run_id_short"] == "12345678"
    assert history[0]["artifact_count"] == 2
    assert detail["prices_observed"]["BTC/USD"] == 69420
    assert detail["metrics_snapshot"]["ending_cash"] == 80000


def test_artifact_and_trade_rows_are_demo_friendly():
    trade_rows = format_trade_rows(
        [
            {
                "ts": "2026-03-31T00:00:00Z",
                "symbol": "ETH/USD",
                "side": "BUY",
                "quantity": 1.2,
                "price": 3210,
                "notional": 3852,
                "reason": "EMA_BULLISH_PULLBACK",
                "pnl": 0.0,
                "artifact_id": "artifact-1",
            }
        ]
    )
    artifact_rows = format_artifact_rows(
        [
            {
                "id": "artifact-1",
                "ts": "2026-03-31T00:00:00Z",
                "artifact_type": "TradeIntent",
                "subject": "ETH/USD",
                "payload_json": '{"symbol": "ETH/USD", "side": "BUY", "quantity": 1.2, "price": 3210, "reason": "EMA_BULLISH_PULLBACK", "risk": {"allowed": true, "reason_codes": []}}',
                "hash_or_digest": "1234567890abcdef1234567890abcdef",
                "path": "artifacts/2026-03-31/artifact-1.json",
            }
        ]
    )
    artifact_summary = format_latest_artifact_summary(
        {
            "id": "artifact-1",
            "ts": "2026-03-31T00:00:00Z",
            "artifact_type": "TradeIntent",
            "subject": "ETH/USD",
            "payload_json": '{"symbol": "ETH/USD", "side": "BUY", "quantity": 1.2, "price": 3210, "reason": "EMA_BULLISH_PULLBACK", "risk": {"allowed": true, "reason_codes": []}}',
            "hash_or_digest": "1234567890abcdef1234567890abcdef",
            "path": "artifacts/2026-03-31/artifact-1.json",
        }
    )

    assert trade_rows[0]["artifact_id"] == "artifact-1"
    assert artifact_rows[0]["signal_reason"] == "EMA_BULLISH_PULLBACK"
    assert artifact_summary["risk_allowed"] is True
