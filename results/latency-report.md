# GPU latency experiment — 2026-09-19 UTC

## Outcome

RTX 4090 benchmark completed. H100 did not finish its pinned PyTorch installation within the allowed startup-to-stop window; it produced zero inference samples. This experiment cannot establish an H100-versus-4090 speed difference.

## Method

Qwen3.5-4B BF16, pinned model/source revisions in deployment.json, unchanged single-inference service. Requests originate from the local workstation through Runpod HTTPS proxy. Synthetic 3-option tool routing, five short warmups after a separately recorded first request. Nearest-rank percentiles; no retries. Long-input groups include their first shape-specific request. Repeated synthetic input is not a quality evaluation.

216 total requests, including first inference and warmup. Percentiles below include successful requests only. Concurrency tests use synchronized bursts.

| Workload | Input tokens | Success / attempts | HTTP P50 / P95 (ms) | Forward P50 / P95 (ms) |
|---|---:|---:|---:|---:|
| short_keepalive | 116 | 50 / 50 | 139.7 / 262.3 | 53.8 / 95.9 |
| short_fresh_connection | 116 | 20 / 20 | 230.1 / 399.9 | 54.6 / 99.6 |
| medium_keepalive | 676 | 30 / 30 | 171.2 / 246.7 | 83.9 / 110.3 |
| long_keepalive | 2496 | 30 / 30 | 505.9 / 614.5 | 288.7 / 298.0 |
| short_concurrency_2 | 116 | 21 / 40 | 153.9 / 428.1 | 65.6 / 115.1 |
| short_concurrency_4 | 116 | 13 / 40 | 158.1 / 543.1 | 64.2 / 72.5 |

First inference after model load: 1606 ms HTTP, 1315 ms forward; excluded from warm latency groups. This is not total Pod cold-start time.

Connection reuse reduced observed short-request median from 230 ms to 140 ms (~39%). Groups were sequential, so this is a single-run observation, not a randomized causal estimate. The server permits one inference at a time: concurrency 2 rejected 19/40 requests (47.5%), concurrency 4 rejected 27/40 (67.5%) with HTTP 429. These fast rejections are not inference throughput.

## H100 limit and resource state

H100 pod n1zzy7wgga9l0v (US-MO-1), $3.49/hour, started 00:47:34.129 UTC and confirmed stopped by 00:56:30.711 UTC: under 8m57s. GPU cost estimate for this bounded attempt: $0.520, excluding earlier setup and storage. The model downloaded, but torch==2.10.0 CUDA 12.8 installation remained unfinished. See h100-setup-incomplete.log and h100-latency-status.json. No GPU performance conclusion can be drawn from installation speed.

Both Pods were confirmed EXITED after the experiment. The H100 has a retained 40 GB persistent disk; the 4090 retains its existing 30 GB network volume. Storage continues billing. H100 setup remains incomplete and does not auto-start an inference service.

## Reproduce after service readiness

```sh
python3 deploy/latency.py --url https://t97hrors0wpvpb-8000.proxy.runpod.net --output results/new-latency.json
```

To obtain a valid cross-GPU comparison, complete the same pinned environment before allocating the next bounded H100 test window; match versions and requests, and separate region/network differences from forward timings.
