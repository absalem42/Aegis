from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import shlex
import subprocess
from typing import Any
from uuid import uuid4

from config import KRAKEN_EXECUTION_MODE_LIVE
from market.kraken_cli import KRAKEN_CLI_PAIR_MAP
from models import ExecutionOutcome, ExecutionRequest

SAFE_KRAKEN_CLI_PAPER_COMMANDS = frozenset({"init", "status", "buy", "sell", "reset"})
SAFE_KRAKEN_CLI_LIVE_COMMANDS = frozenset({"auth", "order"})


class KrakenCliExecutionError(RuntimeError):
    """Raised when the safe Kraken CLI paper execution path is unavailable or malformed."""


@dataclass(slots=True)
class KrakenCliPaperRunner:
    command_prefix: str
    timeout_seconds: float
    command_tokens: list[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.timeout_seconds = max(1.0, float(self.timeout_seconds))
        self.command_tokens = _split_command_prefix(self.command_prefix)

    def run_json(self, paper_command: str, *args: str) -> Any:
        if paper_command not in SAFE_KRAKEN_CLI_PAPER_COMMANDS:
            raise KrakenCliExecutionError(
                f"Kraken CLI paper command is not allowed in Aegis v0: {paper_command}"
            )

        argv = [*self.command_tokens, "paper", paper_command, *[str(arg) for arg in args], "-o", "json"]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                check=False,
                shell=False,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise KrakenCliExecutionError(
                f"Kraken CLI command was not found: {' '.join(self.command_tokens)}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise KrakenCliExecutionError(
                f"Kraken CLI paper command timed out after {self.timeout_seconds:.0f} seconds."
            ) from exc
        except OSError as exc:
            raise KrakenCliExecutionError(f"Kraken CLI paper command failed to start: {exc}") from exc

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if completed.returncode != 0:
            raise KrakenCliExecutionError(_error_message_from_cli_failure(stdout, stderr, completed.returncode))

        payload = _loads_json(stdout)
        if isinstance(payload, dict) and payload.get("error"):
            raise KrakenCliExecutionError(_error_message_from_payload(payload))
        return payload

    def run_live_json(self, command: str, *args: str) -> Any:
        if command not in SAFE_KRAKEN_CLI_LIVE_COMMANDS:
            raise KrakenCliExecutionError(
                f"Kraken CLI live command is not allowed in Aegis v0: {command}"
            )

        argv = [*self.command_tokens, command, *[str(arg) for arg in args], "-o", "json"]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                check=False,
                shell=False,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise KrakenCliExecutionError(
                f"Kraken CLI command was not found: {' '.join(self.command_tokens)}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise KrakenCliExecutionError(
                f"Kraken CLI live command timed out after {self.timeout_seconds:.0f} seconds."
            ) from exc
        except OSError as exc:
            raise KrakenCliExecutionError(f"Kraken CLI live command failed to start: {exc}") from exc

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if completed.returncode != 0:
            raise KrakenCliExecutionError(_error_message_from_cli_failure(stdout, stderr, completed.returncode))

        payload = _loads_json(stdout)
        if isinstance(payload, dict) and payload.get("error"):
            raise KrakenCliExecutionError(_error_message_from_payload(payload))
        return payload


class KrakenCliPaperExecutor:
    provider_name = "Kraken CLI Paper Suite"
    source_type = "cli-paper"
    backend_name = "cli"

    def __init__(self, command_prefix: str, timeout_seconds: float) -> None:
        self.runner = KrakenCliPaperRunner(command_prefix=command_prefix, timeout_seconds=timeout_seconds)

    def availability_note(self) -> str:
        return "Kraken CLI paper execution is available as a local simulation path."

    def ensure_paper_ready(self, starting_cash: float) -> dict[str, Any]:
        try:
            payload = self.runner.run_json("status")
        except KrakenCliExecutionError:
            init_payload = self.runner.run_json(
                "init",
                "--balance",
                _format_decimal(starting_cash),
                "--currency",
                "USD",
            )
            if not isinstance(init_payload, dict):
                raise KrakenCliExecutionError("Kraken CLI paper init did not return a JSON object.")
            return init_payload
        if not isinstance(payload, dict):
            raise KrakenCliExecutionError("Kraken CLI paper status did not return a JSON object.")
        return payload

    def reset_and_init(self, starting_cash: float) -> dict[str, Any]:
        reset_payload = self.runner.run_json("reset")
        init_payload = self.runner.run_json(
            "init",
            "--balance",
            _format_decimal(starting_cash),
            "--currency",
            "USD",
        )
        return {
            "reset": reset_payload,
            "init": init_payload,
        }

    def execute(self, connection, request: ExecutionRequest) -> ExecutionOutcome:
        pair = _pair_for_symbol(request.symbol)
        side = request.side.upper()
        if side == "BUY":
            payload = self.runner.run_json("buy", pair, _format_decimal(request.quantity))
        elif side == "SELL":
            payload = self.runner.run_json("sell", pair, _format_decimal(request.quantity))
        else:
            raise KrakenCliExecutionError(f"Unsupported Kraken CLI paper side: {request.side}")

        order_payload = _extract_order_payload(payload)
        filled_quantity = _extract_numeric(
            order_payload,
            ("filled_qty", "filled_quantity", "volume", "qty", "amount"),
            "Kraken CLI paper filled quantity",
            default=request.quantity,
        )
        fill_price = _extract_numeric(
            order_payload,
            ("avg_fill_price", "fill_price", "price", "last_price"),
            "Kraken CLI paper fill price",
            default=request.price,
        )
        notional = round(filled_quantity * fill_price, 6)
        external_order_id = _extract_optional_string(
            order_payload,
            ("order_id", "id", "paper_order_id", "trade_id"),
        )
        external_status = (
            _extract_optional_string(order_payload, ("status", "state", "result")) or "FILLED"
        )

        return ExecutionOutcome(
            run_id=request.run_id,
            local_order_id=str(uuid4()),
            symbol=request.symbol,
            side=side,
            quantity=round(request.quantity, 6),
            filled_quantity=round(filled_quantity, 6),
            price=round(request.price, 6),
            fill_price=round(fill_price, 6),
            notional=notional,
            artifact_id=request.artifact_id,
            order_type=request.order_type,
            status="FILLED",
            execution_provider=self.provider_name,
            execution_source_type=self.source_type,
            requested_execution_mode=request.requested_execution_mode,
            effective_execution_mode=request.mode_summary.get("effective_execution_mode", request.requested_execution_mode),
            requested_kraken_execution_mode=request.requested_kraken_execution_mode,
            effective_kraken_execution_mode=request.mode_summary.get("effective_kraken_execution_mode"),
            provider_metadata={"paper_response": payload},
            external_order_id=external_order_id,
            external_status=external_status,
        )


class KrakenCliLivePreflightExecutor:
    provider_name = "Kraken CLI Live Preflight"
    source_type = "cli-live-preflight"
    backend_name = "cli"

    def __init__(self, command_prefix: str, timeout_seconds: float) -> None:
        self.runner = KrakenCliPaperRunner(command_prefix=command_prefix, timeout_seconds=timeout_seconds)

    def availability_note(self) -> str:
        return "Kraken live preflight performs auth and validate checks only. No live submit occurs in this milestone."

    def auth_test(self) -> dict[str, Any]:
        payload = self.runner.run_live_json("auth", "test")
        normalized = _extract_auth_payload(payload)
        status_value = str(normalized.get("status", "ok")).strip().lower()
        authenticated = normalized.get("authenticated")
        if authenticated is False or status_value in {"error", "failed", "unauthorized"}:
            raise KrakenCliExecutionError("Kraken CLI auth test failed.")
        return normalized

    def validate_market_order(self, request: ExecutionRequest) -> dict[str, Any]:
        pair = _pair_for_symbol(request.symbol)
        side = request.side.upper().lower()
        if side not in {"buy", "sell"}:
            raise KrakenCliExecutionError(f"Unsupported Kraken CLI live preflight side: {request.side}")
        payload = self.runner.run_live_json(
            "order",
            side,
            pair,
            _format_decimal(request.quantity),
            "--type",
            "market",
            "--validate",
        )
        return _extract_validate_payload(payload)

    def preflight(self, request: ExecutionRequest) -> ExecutionOutcome:
        auth_payload = self.auth_test()
        validate_payload = self.validate_market_order(request)
        external_status = _extract_optional_string(
            validate_payload,
            ("status", "state", "result"),
        ) or "validated"
        return ExecutionOutcome(
            run_id=request.run_id,
            local_order_id=str(uuid4()),
            symbol=request.symbol,
            side=request.side.upper(),
            quantity=round(request.quantity, 6),
            filled_quantity=0.0,
            price=round(request.price, 6),
            fill_price=0.0,
            notional=round(request.quantity * request.price, 6),
            artifact_id=request.artifact_id,
            order_type=request.order_type,
            status="PREFLIGHT_PASSED",
            execution_provider=self.provider_name,
            execution_source_type=self.source_type,
            requested_execution_mode=request.requested_execution_mode,
            effective_execution_mode="kraken_live_preflight",
            requested_kraken_execution_mode=request.requested_kraken_execution_mode,
            effective_kraken_execution_mode=KRAKEN_EXECUTION_MODE_LIVE,
            provider_metadata={
                "auth_test": auth_payload,
                "validate_preflight": validate_payload,
                "requested_notional": round(request.quantity * request.price, 6),
                "no_live_submit_performed": True,
            },
            external_status=external_status,
            auth_test_status="PASSED",
            validate_preflight_status="PASSED",
            live_preflight_status="PREFLIGHT_PASSED",
            notes="Kraken live preflight passed auth and validate checks. No live submit was performed.",
        )

    def execute(self, connection, request: ExecutionRequest) -> ExecutionOutcome:
        return self.preflight(request)


def _split_command_prefix(command_prefix: str) -> list[str]:
    raw = command_prefix.strip()
    if not raw:
        raise KrakenCliExecutionError("AEGIS_KRAKEN_CLI_COMMAND must not be empty.")

    try:
        tokens = shlex.split(raw, posix=os.name != "nt")
    except ValueError as exc:
        raise KrakenCliExecutionError(f"Kraken CLI command is not parseable: {exc}") from exc

    if not tokens:
        raise KrakenCliExecutionError("AEGIS_KRAKEN_CLI_COMMAND must contain a runnable command.")
    return tokens


def _pair_for_symbol(symbol: str) -> str:
    if symbol not in KRAKEN_CLI_PAIR_MAP:
        raise KrakenCliExecutionError(f"Kraken CLI paper execution does not support symbol: {symbol}")
    return KRAKEN_CLI_PAIR_MAP[symbol]


def _loads_json(raw: str) -> Any:
    if not raw:
        raise KrakenCliExecutionError("Kraken CLI paper command returned an empty stdout payload.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KrakenCliExecutionError("Kraken CLI paper command returned invalid JSON.") from exc


def _error_message_from_cli_failure(stdout: str, stderr: str, returncode: int) -> str:
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return _error_message_from_payload(payload)
    if stderr:
        return f"Kraken CLI paper command exited with code {returncode}: {stderr}"
    if stdout:
        return f"Kraken CLI paper command exited with code {returncode}: {stdout}"
    return f"Kraken CLI paper command exited with code {returncode}."


def _error_message_from_payload(payload: dict[str, Any]) -> str:
    error_value = payload.get("error")
    message = payload.get("message")
    if isinstance(error_value, str) and isinstance(message, str):
        return f"{error_value}: {message}"
    if isinstance(message, str):
        return message
    if isinstance(error_value, str):
        return error_value
    if isinstance(error_value, list) and error_value:
        return ", ".join(str(item) for item in error_value)
    return "Kraken CLI paper command returned an unknown JSON error envelope."


def _extract_order_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("result", "order", "trade"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
            if isinstance(nested, list) and nested and isinstance(nested[0], dict):
                return nested[0]
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    raise KrakenCliExecutionError("Kraken CLI paper execution output did not contain an order payload.")


def _extract_auth_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise KrakenCliExecutionError("Kraken CLI auth test did not return a JSON object.")
    for key in ("result", "auth", "status"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    if any(key in payload for key in ("authenticated", "status", "success", "message")):
        return payload
    raise KrakenCliExecutionError("Kraken CLI auth test output was missing expected fields.")


def _extract_validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise KrakenCliExecutionError("Kraken CLI validate preflight did not return a JSON object.")
    for key in ("result", "order", "validation"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    if any(key in payload for key in ("status", "validation", "validated", "message")):
        return payload
    raise KrakenCliExecutionError("Kraken CLI validate preflight output was missing expected fields.")


def _extract_numeric(
    payload: dict[str, Any],
    keys: tuple[str, ...],
    label: str,
    default: float | None = None,
) -> float:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise KrakenCliExecutionError(f"{label} was not numeric.") from exc
    if default is not None:
        return float(default)
    raise KrakenCliExecutionError(f"{label} was missing from Kraken CLI paper output.")


def _extract_optional_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _format_decimal(value: float) -> str:
    return f"{float(value):.10f}".rstrip("0").rstrip(".")
