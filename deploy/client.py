"""Example: python3 deploy/client.py --state '...' --question '...' --option 'yes:Yes' --option 'no:No'."""
import argparse
import json
from pathlib import Path
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="https://t97hrors0wpvpb-8000.proxy.runpod.net")
parser.add_argument("--key-file", type=Path, default=Path(__file__).resolve().parents[1] / ".local/api-key")
parser.add_argument("--state", required=True)
parser.add_argument("--question", required=True)
parser.add_argument("--option", action="append", required=True, help="id:description; 2–16 options")
args = parser.parse_args()
options = []
for item in args.option:
    key, separator, description = item.partition(":")
    if not separator:
        parser.error("Each option must be id:description")
    options.append({"id": key, "description": description})
payload = {"state": args.state, "question": args.question, "options": options}
req = urllib.request.Request(args.url + "/v1/decide", json.dumps(payload).encode(), {
    "Content-Type": "application/json", "User-Agent": "jev-experiment/0.1",
    "Authorization": "Bearer " + args.key_file.read_text().strip()})
with urllib.request.urlopen(req, timeout=120) as response:
    print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
