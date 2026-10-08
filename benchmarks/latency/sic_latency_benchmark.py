"""Benchmark SIC request/reply overhead and a persistent-listener alternative.

This benchmark intentionally uses SIC's real ``SICRedisConnection`` and message
serialization code.  It does not call cloud STT, LLM, or TTS services, so it can
run without API keys and isolates framework/Redis overhead from model latency.

The baseline is the current ``SICRedisConnection.request`` implementation.  It
creates and tears down a Redis pub/sub listener thread for every request.

The proof of concept keeps one reply listener alive and dispatches replies to
waiting requests by ``request_id``.  It is local to this benchmark; it does not
patch the SIC source tree.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Callable


def percentile(sorted_values: list[float], percentage: float) -> float:
    """Return an interpolated percentile from an already-sorted sample."""
    if not sorted_values:
        raise ValueError("Cannot calculate a percentile of an empty sample")
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = (len(sorted_values) - 1) * percentage
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def summarize_ms(samples: list[float]) -> dict[str, float | int]:
    ordered = sorted(samples)
    return {
        "count": len(ordered),
        "min_ms": round(ordered[0], 3),
        "mean_ms": round(statistics.fmean(ordered), 3),
        "p50_ms": round(percentile(ordered, 0.50), 3),
        "p95_ms": round(percentile(ordered, 0.95), 3),
        "max_ms": round(ordered[-1], 3),
    }


def measure(operation: Callable[[], object], iterations: int) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    return samples


def configure_imports(sic_repo: Path, host: str, port: int) -> None:
    if not (sic_repo / "sic_framework").is_dir():
        raise FileNotFoundError(
            f"{sic_repo} does not contain the sic_framework package. "
            "Pass the inner social-interaction-cloud repository directory."
        )
    sys.path.insert(0, str(sic_repo))
    os.environ["DB_IP"] = host
    os.environ["DB_PORT"] = str(port)


def run_benchmark(
    sic_repo: Path,
    host: str,
    port: int,
    iterations: int,
    warmup: int,
    payload_sizes: list[int],
) -> dict[str, object]:
    configure_imports(sic_repo, host, port)

    from sic_framework.core.message_python2 import SICMessage, SICRequest
    from sic_framework.core.sic_redis import SICRedisConnection
    from sic_framework.core.utils import is_sic_instance

    # SIC uses pickle for transport. Pickle must be able to resolve message
    # classes by module-qualified name, so expose these dynamically-created
    # benchmark types at module scope rather than defining local-only classes.
    def echo_request_init(self, payload: bytes) -> None:
        SICRequest.__init__(self)
        self.payload = payload

    def echo_reply_init(self, payload: bytes) -> None:
        self.payload = payload

    EchoRequest = type(
        "EchoRequest",
        (SICRequest,),
        {"__module__": __name__, "__init__": echo_request_init},
    )
    EchoReply = type(
        "EchoReply",
        (SICMessage,),
        {"__module__": __name__, "__init__": echo_reply_init},
    )
    globals()["EchoRequest"] = EchoRequest
    globals()["EchoReply"] = EchoReply

    channel = "benchmark:sic:request_reply"
    server = SICRedisConnection()
    baseline_client = SICRedisConnection()
    persistent_connection = SICRedisConnection()

    def echo(request: EchoRequest) -> EchoReply:
        return EchoReply(request.payload)

    server_handler = server.register_request_handler(
        channel,
        echo,
        name="sic_latency_benchmark_echo_server",
    )

    class PersistentReplyClient:
        """PoC request dispatcher with one subscription for all replies."""

        def __init__(self, connection: SICRedisConnection, reply_channel: str):
            self.connection = connection
            self.reply_channel = reply_channel
            self.pending: dict[int, tuple[threading.Event, queue.Queue]] = {}
            self.lock = threading.Lock()
            self.handler = connection.register_message_handler(
                reply_channel,
                self._receive,
                name="sic_latency_benchmark_persistent_client",
            )

        def _receive(self, reply: SICMessage) -> None:
            if is_sic_instance(reply, SICRequest):
                return
            request_id = getattr(reply, "_request_id", None)
            with self.lock:
                waiter = self.pending.get(request_id)
            if waiter is None:
                return
            event, replies = waiter
            replies.put(reply)
            event.set()

        def request(self, request: SICRequest, timeout: float = 5.0) -> SICMessage:
            event = threading.Event()
            replies: queue.Queue = queue.Queue(maxsize=1)
            request_id = request._request_id
            with self.lock:
                self.pending[request_id] = (event, replies)
            try:
                self.connection.send_message(self.reply_channel, request)
                if not event.wait(timeout):
                    raise TimeoutError(
                        f"Persistent listener timed out for {request.get_message_name()}"
                    )
                return replies.get_nowait()
            finally:
                with self.lock:
                    self.pending.pop(request_id, None)

        def close(self) -> None:
            self.connection.unregister_callback(self.handler)

    persistent_client = PersistentReplyClient(persistent_connection, channel)

    results: dict[str, object] = {
        "environment": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "redis_host": host,
            "redis_port": port,
            "iterations": iterations,
            "warmup": warmup,
            "sic_repo": str(sic_repo.resolve()),
        },
        "raw_redis_ping": {},
        "listener_create_teardown": {},
        "payload_results": [],
    }

    try:
        baseline_client._redis.ping()
        ping_samples = measure(baseline_client._redis.ping, iterations)
        results["raw_redis_ping"] = summarize_ms(ping_samples)

        def listener_lifecycle() -> None:
            handler = baseline_client.register_message_handler(
                "benchmark:sic:listener_lifecycle",
                lambda _message: None,
                name="sic_latency_benchmark_listener_lifecycle",
            )
            baseline_client.unregister_callback(handler)

        listener_samples = measure(listener_lifecycle, iterations)
        results["listener_create_teardown"] = summarize_ms(listener_samples)

        for size in payload_sizes:
            payload = b"x" * size

            # Exercise subscriptions and both paths before collecting samples.
            for _ in range(warmup):
                baseline_client.request(channel, EchoRequest(payload), timeout=5)
                persistent_client.request(EchoRequest(payload), timeout=5)

            def baseline_round_trip() -> None:
                reply = baseline_client.request(
                    channel,
                    EchoRequest(payload),
                    timeout=5,
                )
                if reply.payload != payload:
                    raise AssertionError("Baseline echo payload did not match")

            def persistent_round_trip() -> None:
                reply = persistent_client.request(EchoRequest(payload), timeout=5)
                if reply.payload != payload:
                    raise AssertionError("Persistent echo payload did not match")

            baseline_samples = measure(baseline_round_trip, iterations)
            persistent_samples = measure(persistent_round_trip, iterations)

            def serialize_once() -> None:
                EchoRequest(payload).serialize()

            serialized = EchoRequest(payload).serialize()

            def deserialize_once() -> None:
                SICMessage.deserialize(serialized)

            micro_iterations = max(iterations * 10, 200)
            serialization_samples = measure(serialize_once, micro_iterations)
            deserialization_samples = measure(deserialize_once, micro_iterations)

            baseline_summary = summarize_ms(baseline_samples)
            persistent_summary = summarize_ms(persistent_samples)
            speedup = (
                baseline_summary["p50_ms"] / persistent_summary["p50_ms"]
                if persistent_summary["p50_ms"]
                else None
            )
            results["payload_results"].append(
                {
                    "payload_bytes": size,
                    "serialized_bytes": len(serialized),
                    "current_request": baseline_summary,
                    "persistent_listener_poc": persistent_summary,
                    "p50_speedup_x": round(speedup, 2) if speedup else None,
                    "serialize": summarize_ms(serialization_samples),
                    "deserialize": summarize_ms(deserialization_samples),
                }
            )
    finally:
        persistent_client.close()
        server.unregister_callback(server_handler)
        baseline_client.close()
        persistent_connection.close()
        server.close()

    return results


def print_human_summary(results: dict[str, object]) -> None:
    env = results["environment"]
    print(
        f"SIC latency benchmark: {env['iterations']} measured runs, "
        f"{env['warmup']} warm-up runs"
    )
    ping = results["raw_redis_ping"]
    print(
        f"Raw Redis PING: p50={ping['p50_ms']:.3f} ms, "
        f"p95={ping['p95_ms']:.3f} ms"
    )
    listener = results["listener_create_teardown"]
    print(
        f"Listener create+teardown: p50={listener['p50_ms']:.3f} ms, "
        f"p95={listener['p95_ms']:.3f} ms"
    )
    print()
    print(
        "payload   current p50/p95   persistent p50/p95   p50 speedup   "
        "serialize p50   deserialize p50"
    )
    for item in results["payload_results"]:
        current = item["current_request"]
        persistent = item["persistent_listener_poc"]
        print(
            f"{item['payload_bytes']:>7} B  "
            f"{current['p50_ms']:>7.3f}/{current['p95_ms']:<7.3f} ms  "
            f"{persistent['p50_ms']:>7.3f}/{persistent['p95_ms']:<7.3f} ms  "
            f"{item['p50_speedup_x']:>8.2f}x     "
            f"{item['serialize']['p50_ms']:>8.3f} ms     "
            f"{item['deserialize']['p50_ms']:>8.3f} ms"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sic-repo",
        type=Path,
        required=True,
        help="Path containing the sic_framework package",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument(
        "--payload-sizes",
        type=int,
        nargs="+",
        default=[0, 4096, 65536],
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.iterations < 1 or args.warmup < 0:
        raise ValueError("iterations must be positive and warmup cannot be negative")
    if any(size < 0 for size in args.payload_sizes):
        raise ValueError("payload sizes cannot be negative")

    results = run_benchmark(
        sic_repo=args.sic_repo,
        host=args.host,
        port=args.port,
        iterations=args.iterations,
        warmup=args.warmup,
        payload_sizes=args.payload_sizes,
    )
    print_human_summary(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nJSON results written to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
