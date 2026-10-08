# SIC Pipeline Efficiency and Latency Analysis

**Author:** Semihcan Kadıoğlu

**Date:** 6 October 2026

**Scope:** Social Interaction Cloud (SIC) framework and the NarDial integration

## Executive summary

This investigation identified one measurable framework-level latency issue and
two higher-level opportunities for reducing perceived conversational latency:

1. `SICRedisConnection.request()` creates and destroys a Redis pub/sub listener
   thread for every request. On a local Windows benchmark this lifecycle cost
   had a median trial-level **13.560 ms p50**. A benchmark-only persistent
   reply listener reduced the median trial-level p50 of a small-message SIC
   request from **5.101 ms to 0.501 ms**. The persistent design also had much
   lower and more stable p95 latency.
2. SIC's GPT service already supports token streaming, but NarDial currently
   sends a non-streaming request and waits for the complete response.
3. SIC's ElevenLabs WebSocket implementation receives chunks, but buffers all
   chunks and closes the connection before returning one complete audio message.
   Therefore it does not yet provide end-to-end time-to-first-audio streaming.

The first recommended production change is to add shared latency
instrumentation and replace per-request reply subscriptions with a persistent,
request-ID-based reply dispatcher. After that, the next user-visible improvement
should be an end-to-end LLM-to-TTS streaming path.

## 1. Current pipeline

A representative SIC/NarDial conversational turn is:

```text
Microphone / robot
    -> speech recognition or NLU
    -> SIC Redis request/message transport
    -> optional retrieval
    -> LLM generation
    -> text-to-speech synthesis
    -> SIC transport
    -> speaker / robot
```

SIC provides the distributed component and service layer. NarDial provides
dialogue flow, session state, scripted moves, and provider adapters on top of
SIC.

For interactive systems, total latency is not the only useful metric. The most
important user-facing metrics are:

- **End-of-speech to first response audio**
- **LLM time to first token (TTFT)**
- **TTS time to first audio (TTFA)**
- **End-to-end turn latency**
- Per-stage p50 and p95 latency

## 2. Code-level findings

### 2.1 A listener is created for each synchronous SIC request

Current implementation:

`sic_framework/core/sic_redis.py`, lines 352–413

```python
if block:
    callback_thread = self.register_message_handler(channel, await_reply, ...)

self.send_message(channel, request)
done.wait(timeout)
self.unregister_callback(callback_thread)
```

For every blocking request, SIC:

1. creates a Redis pub/sub object;
2. subscribes to the request/reply channel;
3. starts a callback thread;
4. publishes the request;
5. waits for the matching request ID;
6. unsubscribes and stops the thread.

`register_message_handler()` uses `pubsub.run_in_thread(sleep_time=0.1)`.
This is an I/O polling timeout, not a mandatory 100 ms delay for every message.
The benchmark does not isolate polling, scheduling, and teardown contributions,
so the observed variance cannot be attributed to this setting alone.

This affects repeated calls to services such as GPT and TTS even when the
service itself is already running.

### 2.2 LLM streaming exists in SIC but is not used end to end

`sic_framework/services/llm/openai_gpt.py`, lines 165–218, supports
`GPTRequest(stream=True)` and publishes intermediate `GPTResponse` chunks.

NarDial's `OpenAIGPTProvider.complete()` sends a normal `GPTRequest` and waits
for the complete response. As a result, NarDial cannot begin speech synthesis
from the first complete sentence while the LLM is still generating.

### 2.3 ElevenLabs WebSocket audio is buffered before return

`sic_framework/services/elevenlabs_tts/elevenlabs_tts.py` uses the ElevenLabs
WebSocket endpoint, but currently:

- appends every audio chunk to a list;
- joins all chunks after `isFinal`;
- returns one `AudioMessage`;
- closes the WebSocket after each synthesis call.

This may improve synthesis behavior compared with HTTP batch mode, but it does
not reduce time to first played audio. A true streaming path would publish or
play audio chunks as they arrive and reuse the WebSocket when configuration is
unchanged.

### 2.4 STT end-of-speech latency is configurable

The local Whisper service has a default `pause_threshold=0.8` seconds and
documents the accuracy/latency trade-off. Its default model is
`large-v3-turbo` with `beam_size=5`; smaller models and `beam_size=1` are
available low-latency configurations.

This means a measurable part of conversational delay may come from endpointing
rather than inference. The value should be tuned with noisy-environment tests
instead of reduced unconditionally.

### 2.5 Serialization is not the first conversational latency target

SIC uses Pickle protocol 2 for Python 2/3 compatibility. Protobuf remains useful
for interoperability, schema safety, and eventually removing Python 2 coupling.
However, the local microbenchmark showed serialization below 0.02 ms p50 for
payloads up to 64 KiB. Based on these results, changing serialization is not the
highest-impact first step for text-based conversational latency. Large camera
frames and continuous audio require a separate throughput benchmark before
drawing the same conclusion.

## 3. Benchmark methodology

The included `sic_latency_benchmark.py` uses the actual SIC classes:

- `SICRedisConnection`
- `SICRequest`
- `SICMessage.serialize()` / `deserialize()`
- Redis Pub/Sub request/reply

It starts an echo request handler and compares:

1. raw Redis `PING`;
2. listener creation and teardown;
3. current `SICRedisConnection.request()`;
4. a proof-of-concept persistent reply listener;
5. serialization and deserialization.

Test environment:

- Windows
- Python 3.12.13
- Redis on `127.0.0.1:6389`
- 20 warm-up runs per trial
- 200 measured runs for each payload size per trial
- 3 independent trials
- Sequential request workload

The raw trial results and aggregated trial-level summary are stored under
`results/`.

Measurement boundaries and limitations:

- Request timings cover the complete client call, including listener cleanup
  after the baseline receives its reply; they are not first-reply-arrival timings.
- The baseline block runs before the persistent-listener block. Ordering is not
  randomized, and concurrency, disconnects and robot hardware are not tested.
- Both methods share a local echo server, and the persistent subscription is
  already active during the baseline measurements.
- Payloads are byte strings, not image arrays or streaming audio. Serialization
  timings include constructing an `EchoRequest` and its request ID.
- A zero-byte payload still carries serialized message metadata.
- Reported values are medians of three trial-level percentile summaries, not
  percentiles calculated from a pooled set of 600 requests.

## 4. Results

### Infrastructure baselines

The table reports the median of the three trial-level summaries. Parentheses
show the range between trials.

| Measurement | p50 median (range) | p95 median (range) |
|---|---:|---:|
| Raw Redis PING | 0.056 ms (0.049–0.134) | 0.062 ms (0.057–0.279) |
| Listener create + teardown | 13.560 ms (1.605–15.729) | 17.756 ms (16.956–32.732) |

### SIC request/reply results

| Payload | Current p50 median (range) | Current p95 median (range) | Persistent p50 median (range) | Persistent p95 median (range) | Ratio of median p50 |
|---:|---:|---:|---:|---:|---:|
| 0 B | 5.101 ms (3.003–14.418) | 117.262 ms (27.364–123.580) | 0.501 ms (0.500–0.786) | 0.837 ms (0.658–1.369) | 10.18× |
| 4 KiB | 6.846 ms (3.443–16.065) | 38.862 ms (27.458–106.647) | 0.694 ms (0.485–0.899) | 0.891 ms (0.715–1.331) | 9.87× |
| 64 KiB | 14.694 ms (4.254–14.763) | 33.003 ms (28.851–34.774) | 1.541 ms (1.451–2.241) | 1.841 ms (1.836–3.503) | 9.54× |

### Serialization results

Across all three trials, serialization and deserialization p50 remained at or
below 0.013 ms for payloads up to 64 KiB.

### Interpretation

For small and medium request payloads, listener lifecycle overhead is much
larger than serialization and raw Redis latency. The persistent-listener PoC
therefore demonstrates a credible core optimization opportunity.

This does **not** mean a complete robot conversation will be 10× faster. Cloud
STT, LLM and TTS calls may take hundreds or thousands of milliseconds. The
result shows that the per-request subscription design adds measurable and
variable local framework overhead, while one persistent subscription remains
at sub-millisecond p50 for small payloads. Redis PING uses a different protocol
path and is only a reference, not an equivalent request/reply baseline. Exact
savings are platform and load dependent.

## 5. Recommended changes

### Priority 0 — Add shared latency instrumentation

Add structured timings without logging user content:

```text
request_id=<id> component=GPT operation=request total_ms=...
request_id=<id> component=GPT operation=provider_call provider_ms=...
request_id=<id> component=GoogleTTS operation=synthesis provider_ms=...
```

Recommended events:

- connector request started;
- service received request;
- provider/API execution started and finished;
- reply published;
- client received reply;
- first stream token/audio chunk;
- final stream token/audio chunk.

Use `time.perf_counter_ns()` for durations measured within one process. Use the
existing request ID to correlate distributed events. Wall-clock comparisons
between machines require clock synchronization and should not replace local
monotonic durations.

### Priority 1 — Persistent reply dispatcher in `SICRedisConnection`

Replace one listener per request with one long-lived reply subscription and a
thread-safe map:

```text
request_id -> waiting event/future/queue
```

Production requirements:

- support multiple concurrent requests;
- register the listener before publishing requests;
- remove pending entries in `finally`, including timeouts;
- fail all pending requests on disconnect;
- prevent unbounded pending-request growth;
- maintain Python 2 compatibility where still required;
- include sequential, concurrent, timeout and shutdown tests.

Suggested acceptance criteria:

- at least 50% lower p50 framework request latency on loopback;
- no regression in response matching;
- no leaked callback threads or pending entries after timeout;
- correct behavior with at least 20 concurrent requests;
- benchmark results reported as p50 and p95.

### Priority 2 — End-to-end LLM-to-TTS streaming

Build on SIC's existing GPT chunk output:

1. expose a streaming connector API to consumers;
2. accumulate tokens until a safe sentence boundary;
3. enqueue completed sentences for TTS;
4. begin playback while the LLM continues generating;
5. support cancellation and interruption;
6. measure end-of-speech to first audio, not only total duration.

This should improve perceived responsiveness more than low-level transport
changes, but it is a larger cross-service change.

### Priority 3 — True streaming TTS and connection reuse

For ElevenLabs:

- reuse compatible WebSocket sessions;
- emit PCM chunks instead of joining all chunks before returning;
- add bounded buffering/backpressure;
- stream chunks to compatible speaker actuators;
- fall back to batch mode for unsupported devices;
- retain NarDial's TTS cache for fixed scripted lines.

### Priority 4 — Tune STT and model configurations per deployment

Benchmark combinations rather than choosing one global configuration:

- Local Whisper `pause_threshold`: e.g. 0.4, 0.6, 0.8 seconds;
- `beam_size=1` versus `beam_size=5`;
- `base`, `small`, and `large-v3-turbo` models;
- cloud versus local STT;
- clean versus noisy environments.

Report both latency and transcription quality. Faster endpointing that cuts off
children or fails in classroom noise is not a successful optimization.

## 6. Proposed end-to-end experiment

Use one representative desktop conversation demo before moving to robot
hardware.

For each configuration:

1. run 5 cold/warm-up turns;
2. collect 20 or more measured turns;
3. use the same prompts and audio inputs;
4. report p50 and p95;
5. record quality failures separately;
6. repeat on one target robot after the desktop pipeline is stable.

Recommended comparison:

```text
A: current non-streaming pipeline
B: persistent SIC reply listener
C: persistent listener + LLM streaming
D: persistent listener + LLM/TTS streaming
```

Metrics:

- end-of-user-speech to final transcript;
- LLM TTFT and completion time;
- retrieval time, when enabled;
- TTS TTFA and completion time;
- first speaker playback timestamp;
- end-to-end first-response latency;
- transcription and response-quality failures.

## 7. Risks and trade-offs

- A persistent dispatcher is more stateful than the current implementation and
  needs careful timeout and shutdown handling.
- Streaming adds cancellation, sentence segmentation, backpressure and ordering
  complexity.
- Smaller STT/LLM models may reduce quality.
- Lower speech endpointing thresholds may truncate users in noisy classrooms.
- Caching helps scripted content but has limited value for unique LLM outputs.
- Local loopback benchmarks do not represent networked robot deployments.

## 8. Proposed GitHub issues

### SIC issue

**Title:** Reuse a persistent reply subscription for SIC request/reply calls

**Summary:** `SICRedisConnection.request()` currently creates and destroys a
pub/sub listener thread for each call. A local 200-run benchmark measured
5.101–6.846 ms median trial-level p50 for small requests, compared with
0.501–0.694 ms using a persistent-listener proof of concept. Implement a
thread-safe request-ID
dispatcher and add sequential, concurrent, timeout and shutdown tests.

### SIC instrumentation issue

**Title:** Add structured per-stage latency metrics to SIC services

**Summary:** Add request-ID-correlated monotonic timings for connector transport,
service queueing, provider execution, and first/final stream chunks. Provide a
benchmark example that reports p50 and p95 without logging user content.

### NarDial issue

**Title:** Consume SIC GPT streaming responses and measure time to first speech

**Summary:** SIC supports streaming GPT chunks, but NarDial's OpenAI provider
currently waits for a complete response. Design a streaming provider interface,
sentence-level TTS queue and cancellation behavior; compare time to first spoken
audio with the current implementation.

## 9. Deliverables

- `sic_latency_benchmark.py` — runnable demo and persistent-listener PoC
- `results/local-windows-trial-*.json` — three raw benchmark trials
- `results/local-windows-summary.json` — aggregated trial-level results
- this report — findings, priorities, risks and next experiment

## Conclusion

The current evidence supports improving SIC's request/reply lifecycle before
changing serialization. The largest likely user-visible gain, however, requires
using SIC's existing LLM streaming capability together with genuinely streaming
TTS and playback. The recommended order is:

1. instrumentation;
2. persistent reply dispatcher;
3. LLM-to-TTS streaming;
4. STT/model tuning with quality evaluation;
5. serialization migration as a separate compatibility and maintainability
   project unless larger-payload benchmarks show a latency need.
