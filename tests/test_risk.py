from config import Settings
from models import Signal
from risk.engine import RiskEngine


def make_signal(action: str) -> Signal:
    return Signal(
        symbol="BTC/USD",
        action=action,
        reason="TEST_SIGNAL",
        indicators={"price": 100.0},
        should_execute=True,
    )


def test_risk_blocks_when_kill_switch_enabled(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        kill_switch=True,
    )
    decision = RiskEngine(settings).assess(
        signal=make_signal("BUY"),
        quantity=1.0,
        price=100.0,
        cash_balance=10000.0,
        open_positions=0,
        existing_position_qty=0.0,
        daily_drawdown=0.0,
        consecutive_losses=0,
    )

    assert not decision.allowed
    assert "KILL_SWITCH_ENABLED" in decision.reason_codes


def test_risk_blocks_after_two_consecutive_losses(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
        cooldown_after_losses=2,
    )
    decision = RiskEngine(settings).assess(
        signal=make_signal("BUY"),
        quantity=0.1,
        price=100.0,
        cash_balance=10000.0,
        open_positions=0,
        existing_position_qty=0.0,
        daily_drawdown=0.0,
        consecutive_losses=2,
    )

    assert not decision.allowed
    assert "COOLDOWN_ACTIVE" in decision.reason_codes


def test_risk_blocks_sell_without_position(tmp_path):
    settings = Settings(
        db_path=tmp_path / "aegis.db",
        artifact_dir=tmp_path / "artifacts",
    )
    decision = RiskEngine(settings).assess(
        signal=make_signal("SELL"),
        quantity=1.0,
        price=100.0,
        cash_balance=10000.0,
        open_positions=0,
        existing_position_qty=0.0,
        daily_drawdown=0.0,
        consecutive_losses=0,
    )

    assert not decision.allowed
    assert "NO_OPEN_POSITION" in decision.reason_codes
