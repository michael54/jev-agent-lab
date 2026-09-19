"""Bounded HTTP latency benchmark. Stdlib only; never saves credentials."""
import argparse
import concurrent.futures
import datetime
import http.client
import json
import math
import pathlib
import threading
import time
import urllib.parse
from collections import Counter

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', required=True)
parser.add_argument('--key-file', default='.local/api-key')
parser.add_argument('--output', required=True)
args = parser.parse_args()
url = urllib.parse.urlsplit(args.url)
key = pathlib.Path(args.key_file).read_text().strip()
local = threading.local()
rows = []

def request(state, fresh=False):
    if fresh or not getattr(local, 'conn', None):
        cls = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
        local.conn = cls(url.hostname, url.port, timeout=45)
    payload = {'id': 'latency', 'state': state, 'question': 'Which tool should be used next?',
               'options': [{'id': 'weather', 'description': 'Look up live weather'},
                           {'id': 'calculator', 'description': 'Perform arithmetic'},
                           {'id': 'files', 'description': 'Read local files'}]}
    start = time.perf_counter()
    try:
        local.conn.request('POST', '/v1/decide', json.dumps(payload),
                           {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                            'User-Agent': 'jev-latency/0.1'})
        response = local.conn.getresponse()
        data = json.loads(response.read())
        result = {'status': response.status, 'http_seconds': time.perf_counter() - start}
        for field in ('forward_seconds', 'total_seconds', 'input_tokens', 'choice', 'detail'):
            if field in data:
                result[field] = data[field]
        if fresh:
            local.conn.close()
            local.conn = None
        return result
    except Exception as error:
        local.conn.close()
        local.conn = None
        return {'status': 'transport_error', 'error_type': type(error).__name__,
                'http_seconds': time.perf_counter() - start}

def stats(values):
    values = sorted(values)
    if not values:
        return None
    return {k: values[max(0, math.ceil(len(values) * p) - 1)]
            for k, p in [('p50', .5), ('p95', .95), ('max', 1)]}

def group(name, state, count, concurrency=1, fresh=False):
    begin = time.perf_counter()
    if concurrency == 1:
        samples = [request(state, fresh) for _ in range(count)]
    else:
        # Synchronized bursts expose rejection behavior without automatic retries.
        samples = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            for _ in range(count // concurrency):
                barrier = threading.Barrier(concurrency)
                def one():
                    barrier.wait()
                    return request(state)
                futures = [pool.submit(one) for _ in range(concurrency)]
                samples.extend(f.result() for f in futures)
    elapsed = time.perf_counter() - begin
    ok = [s for s in samples if s['status'] == 200]
    summary = {'name': name, 'count': len(samples), 'concurrency': concurrency,
               'status_counts': dict(Counter(str(s['status']) for s in samples)),
               'elapsed_seconds': elapsed, 'successful_requests_per_second': len(ok) / elapsed,
               'input_tokens': sorted(set(s['input_tokens'] for s in ok)),
               'choices': dict(Counter(s['choice'] for s in ok))}
    for field in ('http_seconds', 'forward_seconds', 'total_seconds'):
        summary[field] = stats([s[field] for s in ok])
    rows.append({'summary': summary, 'samples': samples})
    print(json.dumps(summary), flush=True)

short = 'Please find the current weather in Tokyo.'
medium = ('Earlier task completed. The agent read a document and saved its summary. ' * 40) + short
long = ('Earlier task completed. The agent read a document and saved its summary. ' * 170) + short
first = request(short)
if first['status'] != 200:
    raise SystemExit('First inference failed: ' + json.dumps(first))
warmup = [request(short) for _ in range(5)]
group('short_keepalive', short, 50)
group('short_fresh_connection', short, 20, fresh=True)
group('medium_keepalive', medium, 30)
group('long_keepalive', long, 30)
group('short_concurrency_2', short, 40, concurrency=2)
group('short_concurrency_4', short, 40, concurrency=4)
report = {'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'url': args.url, 'first_inference': first, 'warmup': warmup,
          'notes': 'Nearest-rank percentiles of successful requests only. No retries. '
                   'Concurrency uses synchronized bursts. Synthetic latency workload, not quality evaluation.',
          'groups': rows}
pathlib.Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
