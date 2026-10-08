# SIC latency and pipeline efficiency analysis

This folder contains a reproducible benchmark and a short technical report for
the SIC action item:

1. Investigate ways to make the stack/pipeline more efficient, especially
   latency.
2. Prepare a document, presentation, or demo for the proposed changes.

## What the demo measures

`sic_latency_benchmark.py` uses SIC's real Redis connection and message
serialization code. It compares:

- raw Redis `PING` latency;
- the current `SICRedisConnection.request()` implementation;
- a proof-of-concept request dispatcher that reuses one persistent reply
  listener;
- SIC serialization and deserialization time at different payload sizes.

It deliberately avoids cloud STT, LLM, and TTS calls. This isolates SIC
framework overhead, runs without API keys, and produces reproducible results.
The checked-in results contain three independent trials of 200 measured runs;
`results/local-windows-summary.json` reports medians and ranges across trials.

## Run the demo

From the root of the `social-interaction-cloud` repository, start a local Redis
instance on a test-only port:

```powershell
redis-server --port 6389 --bind 127.0.0.1 --save '""' --appendonly no
```

Run the benchmark in an environment where SIC's core dependencies are
installed:

```powershell
python .\benchmarks\latency\sic_latency_benchmark.py `
  --sic-repo . `
  --port 6389 `
  --iterations 50 `
  --warmup 5 `
  --output .\benchmarks\latency\results\local.json
```

For an isolated temporary environment:

```powershell
uv run --no-project `
  --with redis --with six --with numpy --with pillow `
  --with paramiko --with scp --with python-dotenv --with pathlib `
  python .\benchmarks\latency\sic_latency_benchmark.py `
  --sic-repo . --port 6389 `
  --output .\benchmarks\latency\results\local.json
```

## Interpretation

The persistent-listener implementation is a benchmark-only proof of concept.
It demonstrates the potential benefit of avoiding one pub/sub subscription and
one callback thread per request. A production implementation requires lifecycle,
concurrency, timeout, disconnect, Python 2 compatibility, and regression tests.

See `SIC_PIPELINE_EFFICIENCY_REPORT.md` for findings and recommendations.
