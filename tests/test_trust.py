from config import Settings
from models import ExecutionOutcome
from proof.agent_identity import build_agent_identity, build_validation_readiness
from proof.execution_receipt import build_execution_receipt
from proof.trade_intent import build_trade_intent


def test_build_agent_identity_includes_local_metadata(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        agent_id="aegis-demo",
        agent_name="Aegis Demo Agent",
        agent_version="0.2.0",
    )
    identity = build_agent_identity(
        settings,
        {
            "requested_market_data_mode": "mock",
            "effective_market_data_mode": "mock",
            "requested_execution_mode": "paper",
            "effective_execution_mode": "paper",
            "requested_kraken_backend": None,
            "effective_kraken_backend": None,
            "kraken_cli_status": "NOT_REQUESTED",
        },
    )

    assert identity["agent_id"] == "aegis-demo"
    assert identity["agent_name"] == "Aegis Demo Agent"
    assert identity["effective_modes"]["execution_mode"] == "paper"
    assert "erc8004-ready-structure" in identity["capabilities"]


def test_trade_intent_contains_agent_and_validation_metadata():
    from models import RiskDecision, Signal

    signal = Signal(
        symbol="BTC/USD",
        action="BUY",
        reason="EMA_BULLISH_BREAKOUT",
        indicators={"price": 69420.0, "ema20": 68000.0},
        should_execute=True,
    )
    risk = RiskDecision(
        allowed=True,
        reason_codes=[],
        quantity=0.1,
        price=69420.0,
        side="BUY",
    )
    payload = build_trade_intent(
        run_id="run-123",
        signal=signal,
        risk_decision=risk,
        quantity=0.1,
        price=69420.0,
        latest_price=69420.0,
        mode_summary={
            "requested_market_data_mode": "mock",
            "effective_market_data_mode": "mock",
            "requested_execution_mode": "paper",
            "effective_execution_mode": "paper",
            "requested_kraken_backend": None,
            "effective_kraken_backend": None,
            "kraken_cli_status": "NOT_REQUESTED",
        },
        agent_identity={
            "agent_id": "aegis-demo",
            "agent_name": "Aegis Demo Agent",
            "version": "0.2.0",
            "capabilities": ["paper-trading"],
            "execution_mode": "paper",
            "market_data_mode": "mock",
        },
    )

    assert payload["agent"]["agent_id"] == "aegis-demo"
    assert payload["signal"]["indicators"]["price"] == 69420.0
    assert payload["risk"]["summary"] == "ALLOWED"
    assert payload["market_data"]["backend"] is None
    assert payload["market_data"]["kraken_cli_status"] == "NOT_REQUESTED"
    assert payload["market_data"]["provider"] is None
    assert payload["validation_readiness"]["checks"]["has_agent_identity"] is True


def test_validation_readiness_reports_missing_execution_link():
    readiness = build_validation_readiness(
        {
            "agent": {"agent_id": "aegis-demo"},
            "signal": {"reason": "EMA", "indicators": {"price": 1}},
            "risk": {"allowed": True, "summary": "ALLOWED"},
            "modes": {"effective_execution_mode": "paper"},
            "run_id": "run-123",
        },
        has_execution_outcome_linkage=False,
    )

    assert readiness["profile"] == "local-erc8004-readiness"
    assert readiness["checks"]["has_agent_identity"] is True
    assert readiness["checks"]["has_execution_outcome_linkage"] is False


def test_execution_receipt_links_trade_intent_and_execution_metadata():
    outcome = ExecutionOutcome(
        run_id="run-123",
        local_order_id="order-123",
        symbol="BTC/USD",
        side="BUY",
        quantity=0.1,
        filled_quantity=0.1,
        price=69420.0,
        fill_price=69420.0,
        notional=6942.0,
        artifact_id="artifact-intent",
        order_type="market",
        status="FILLED",
        execution_provider="Kraken CLI Paper Suite",
        execution_source_type="cli-paper",
        requested_execution_mode="kraken",
        effective_execution_mode="kraken",
        requested_kraken_execution_mode="paper",
        effective_kraken_execution_mode="paper",
        provider_metadata={"paper_response": {"status": "filled"}},
        external_order_id="paper-123",
        external_status="FILLED",
    )
    payload = build_execution_receipt(
        run_id="run-123",
        symbol="BTC/USD",
        trade_intent_artifact_id="artifact-intent",
        outcome=outcome,
        persisted={
            "order_id": "order-123",
            "trade_id": "trade-123",
            "status": "FILLED",
            "pnl": 0.0,
            "filled_quantity": 0.1,
            "fill_price": 69420.0,
        },
        mode_summary={
            "requested_execution_mode": "kraken",
            "effective_execution_mode": "kraken",
            "requested_kraken_execution_mode": "paper",
            "effective_kraken_execution_mode": "paper",
        },
        agent_identity={"agent_id": "aegis-demo", "agent_name": "Aegis Demo Agent"},
        safety_snapshot={"status": "KRAKEN_PAPER_ACTIVE"},
    )

    assert payload["trade_intent_artifact_id"] == "artifact-intent"
    assert payload["execution"]["execution_provider"] == "Kraken CLI Paper Suite"
    assert payload["execution"]["local_order_id"] == "order-123"
    assert payload["validation_readiness"]["checks"]["has_execution_outcome_linkage"] is True
