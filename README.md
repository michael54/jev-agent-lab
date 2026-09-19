# Jev API and SemIf on Runpod

## Official Jev API

`deploy/jev_client.py` calls TypeSafe's official hosted Jev model. It requires
Python 3.9+ with no extra dependencies. Credentials are read first from
`TYPESAFE_API_KEY`, then from `.local/typesafe-api-key` (Git-ignored; use mode 0600).

```sh
python3 deploy/jev_client.py \
  --state '请求返回 HTTP 429，服务器要求5秒后重试。' \
  --question '下一步应该怎么做？' \
  --option 'retry:等待5秒后重试' \
  --option 'done:报告任务成功' \
  --option 'review:信息不足，需要人工判断'
```

Add `--dry-run` to inspect the request without calling the API. `--model` defaults
to `jev-latest`. The client returns the original answers, probability distribution,
confidence, model and usage; it does not execute the selected action. Requests time
out after 30 seconds per attempt; HTTP 429/529 get up to two backoff retries.

For code integrations, batch independent questions over shared state:

```python
from deploy.jev_client import evaluate

result = evaluate(
    {"message": "Please refund the duplicate invoice charge."},
    {
        "department": {
            "type": "choice",
            "instructions": "Which team should handle the message?",
            "criteria": {"billing": "Payments and refunds", "other": "Other requests"},
        },
        "refund_requested": {
            "type": "noul",
            "instructions": "Does the message explicitly request a refund?",
        },
    },
)
print(result["answers"])
```

Confidence describes the distribution, not a guarantee of correctness. Evaluate
thresholds on your own cases before automating actions. Official references:
[HTTP API](https://docs.typesafe.ai/api),
[Choice](https://docs.typesafe.ai/primitives/choice).

## Self-hosted SemIf experiment

Self-hosted decision API using Qwen3.5-4B BF16 and SemIf's `direct` scoring path.
Model and source commits are pinned in `deployment.json`; this is an independent
Jev-style implementation, not TypeSafe's model or API-compatible service.

## Verified deployment status

Deployment and automatic startup after restart were verified on 2026-09-18
(America/Los_Angeles). The Pod is now **stopped** to avoid ongoing GPU charges;
the API is unavailable until it is started again. Cached weights and the Python
environment remain on the network volume. A future start depends on GPU availability.

- Upstream tests: 15 passed; published artifact verification: 69 claims checked.
- Six handcrafted English/Chinese smoke cases: 6/6 correct before and after restart.
- Initial warm HTTP latency: median 0.317 seconds, range 0.184–0.517 seconds.
- Missing token rejected with 401; duplicate option IDs rejected with 422.
- Reports and exact installed packages are saved in `results/`.
- Billing API returned no records immediately after the run; this is not evidence
  that compute was free. GPU spend is estimated at roughly $0.10 for this short run,
  plus storage, pending the provider's billing record.

## Use

When the Pod is running and the model has loaded:

```sh
python3 deploy/client.py \
  --state '请求返回 HTTP 429，服务器要求5秒后重试。' \
  --question '下一步应该怎么做？' \
  --option 'retry:等待5秒后重试' \
  --option 'done:报告任务成功'
```

- Base URL: `https://t97hrors0wpvpb-8000.proxy.runpod.net`
- `GET /health`: readiness, model and source revisions.
- `POST /v1/decide`: requires `Authorization: Bearer <key>`.
- The client reads the key from `.local/api-key`; never commit or paste that file.
- Private SSH key: `.local/runpod_ed25519`; both keys are excluded by `.gitignore`.
- Inputs: `state` (nonempty text/object/array), `question`, 2–16 `options`
  containing unique `id` and `description`; optional request `id`.
- Limit: 4,096 model input tokens. Overlength input is rejected, never truncated.
- One inference at a time. Busy requests return 429; retry after one second.
- Results contain `choice`, `option_ids`, `probabilities`, model timing and provenance.
  These probabilities are conditional option scores, not calibrated correctness.

## Infrastructure and costs

- Pod: `t97hrors0wpvpb`, Secure Cloud RTX 4090, US-IL-1.
- GPU quote at creation: $0.74/hour, plus disk. Stopping releases GPU billing.
- Network volume: `xqsdvem5tj`, 30 GB Standard, approximately $2.10/month,
  continues billing while stopped. Data is in `/workspace/jev`.
- Container disk: 20 GB, temporary; model, code, environment and logs use the network volume.
- This first deployment is a bounded experiment, not a 24/7 service.
- Resume via Runpod or ask the agent to start this Pod. After resume, wait for
  `/health`; loading cached weights can take time. SSH public port may change.
- The restart command is `bash /workspace/jev/boot.sh`, configured on the Pod.
  It initializes the image's SSH service and starts the model using the saved environment.
- Stopping preserves the network volume. Deleting the volume permanently removes
  the remote model/cache/environment; keep it for subsequent experiments.

## Reproduction

Upstream: https://github.com/TheoLeeCJ/SemIf

Source commit: `b9cb32537e78be65f19abfcb1de8fc504b627d84`

Model: `Qwen/Qwen3.5-4B`

Model revision: `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`

`deploy/setup.sh` creates an isolated environment on the official Runpod PyTorch
CUDA 12.8 image, installs the pinned upstream dependencies, runs upstream tests,
verifies published checksums, and starts the API. Installed package versions are
recorded on the Pod in `/workspace/jev/installed.txt`.

```sh
python3 deploy/smoke.py \
  https://t97hrors0wpvpb-8000.proxy.runpod.net \
  .local/api-key results/new-smoke-report.json
```

Reports are create-only. The six handcrafted English/Chinese cases are smoke
tests, not an unbiased benchmark of real agent performance.

## H100 versus 4090 latency experiment

See [the measured comparison](results/latency-report.md) and raw samples in
`results/latency-4090.json` / `results/latency-h100.json`. The successful H100
retry completed within 3m35s and is stopped. Identical Python packages were used.
Median forward time for 116 / 676 / 2496 input tokens was 54 / 84 / 289 ms on
4090 versus 46 / 55 / 148 ms on H100. Network regions and test times differ.
The reference implementation still lacks optimized recurrent kernels; these
measurements do not represent fully optimized GPU serving performance.
