# H100 vs RTX 4090 latency — 2026-09-19 UTC

## Result

The H100 retry completed successfully in under 3m35s of allocation time. Earlier H100 installation failure was an environment-preparation problem, not an inference failure. Switching package installation from remotely backed workspace storage to container-local storage, on another host, allowed the same dependencies to install quickly. The evidence implicates the old storage/install path; changing hosts means storage alone was not isolated.

Both runs used the identical deploy/latency.py script: 216 requests each, including one first inference and five short warmups. The model/source revisions and full installed Python package lists match exactly. Qwen3.5-4B BF16; no generated answer tokens. All sequential measured requests succeeded. Six English/Chinese H100 smoke cases passed, plus auth/validation checks; 11 core upstream tests passed. The original 4090 deployment ran the larger 15-test upstream suite.

## Warm serial latency

All timings in milliseconds. Each pair is P50 / P95; nearest-rank percentiles.

| Workload | Tokens | Samples per GPU | 4090 forward | H100 forward | 4090 HTTP | H100 HTTP |
|---|---:|---:|---:|---:|---:|---:|
| short_keepalive | 116 | 50 | 53.8 / 95.9 | 46.0 / 52.7 | 139.7 / 262.3 | 199.3 / 406.8 |
| short_fresh_connection | 116 | 20 | 54.6 / 99.6 | 46.1 / 60.1 | 230.1 / 399.9 | 283.1 / 969.2 |
| medium_keepalive | 676 | 30 | 83.9 / 110.3 | 55.4 / 62.6 | 171.2 / 246.7 | 134.0 / 215.4 |
| long_keepalive | 2496 | 30 | 288.7 / 298.0 | 148.5 / 148.8 | 505.9 / 614.5 | 257.0 / 311.9 |

H100 reduced median forward time by about 15% for 116 tokens, 34% for 676 tokens, and 49% for 2496 tokens (1.94x forward throughput for that serial long-input workload). At $3.49/hour versus $0.74/hour, it costs 4.72x as much per allocated hour. It is a latency improvement for longer prompts, not a demonstrated cost-efficiency improvement.

HTTP results include local-to-Runpod transport, TLS, proxying, application overhead, and inference. The GPUs are in different regions (4090 US-IL-1, H100 US-MO-1), different hosts, and tested at different times. Short H100 HTTP P50 was worse despite faster forward execution. Do not interpret HTTP differences as pure GPU speed or claim a universal H100 multiplier. Single-run synthetic prompts; not a general model-quality benchmark.

## Concurrency and cold first request

The unchanged server admits only one inference and immediately rejects busy requests with 429. At concurrency 2, both runs rejected 19/40. At concurrency 4, 4090 rejected 27/40 and H100 29/40. No retries. Rejected requests are excluded from latency percentiles and cannot be counted as successful throughput.

First inference after readiness (excluded from warm groups): 4090 HTTP 1606 ms / forward 1315 ms; H100 HTTP 1170 ms / forward 429 ms. These are first-request timings, not complete Pod cold-start measurements.

## Remaining optimization opportunity

H100 runtime logged reference-PyTorch fallbacks because causal_conv1d and flash-linear-attention are not installed. Both exact package manifests lack these packages. The reported results therefore compare the current baseline implementation, not fully optimized serving stacks. Optimized kernels should be evaluated before treating expensive GPU upgrades as the only way to reduce latency.

## Allocation and costs

Successful H100: 9hrzm168da5rxp, US-MO-1, NVIDIA H100 80GB HBM3, driver 580.126.09. Started 02:40:04.172Z, stopped confirmed 02:43:38.819Z (214.647 seconds, under 3m35s). GPU cost estimate $0.208 excluding disk and earlier attempts. Automatic stop guard was cancelled only after confirmed manual stop. Container-local 40 GB disk; no additional persistent volume created. This temporary Pod is stopped and has no persistent inference environment. Recreate/reinstall from setup-benchmark-local.sh for future runs.

Original H100 n1zzy7wgga9l0v could not resume due to no free GPUs on its host. It remains stopped, with its existing 40 GB persistent disk retained. The prior bounded installation attempt and its logs are preserved in h100-latency-status.json and h100-setup-incomplete.log; those historical records do not describe this successful retry. The 4090 remains stopped; its 30 GB network volume is retained. Retained persistent storage continues billing.

## Reproduction

```sh
# On a fresh GPU Pod after copying SemIf, server.py and api-key:
bash deploy/setup-benchmark-local.sh
# From the client after /health reports ready:
python3 deploy/latency.py --url https://POD_ID-8000.proxy.runpod.net --output results/new-latency.json
```

The setup script expects copied files in /workspace/jev; run it there or copy it there. The model and package versions remain pinned. Raw per-request samples are in latency-4090.json and latency-h100.json; package manifests are installed.txt and h100-installed.txt.
