"""Official Jev API client, using only the Python standard library."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
KEY_FILE = Path(__file__).resolve().parents[1] / ".local/typesafe-api-key"


class JevError(RuntimeError):
    """A request failed; no decision should be acted on."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def evaluate(state, questions, model="jev-latest", key_file=KEY_FILE):
    """Ask multiple independent typed questions in one request; retain raw answers."""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        try:
            key = Path(key_file).read_text().strip()
        except OSError:
            raise JevError("Set TYPESAFE_API_KEY or save a key in .local/typesafe-api-key.") from None
    if not key or any(char.isspace() for char in key):
        raise JevError("API key is empty or contains whitespace.")
    if not isinstance(state, (str, dict, list)) or not state:
        raise ValueError("state must be a nonempty string, object or array")
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a nonempty object")
    body = json.dumps({"model": model, "state": state, "questions": questions},
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    request = urllib.request.Request(ENDPOINT, body, {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "User-Agent": "jev-local-client/1.0",
    })
    opener = urllib.request.build_opener(NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=30) as response:
                result = json.load(response)
            if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
                raise JevError("API returned an invalid response.")
            if set(result["answers"]) != set(questions):
                raise JevError("API response does not match the requested question IDs.")
            return result
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            if status in (429, 529) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            hints = {401: "Check the API key.", 403: "Check account access.",
                     422: "Check the request schema.", 429: "Rate limited; retry later.",
                     529: "Service overloaded; retry later."}
            raise JevError("TypeSafe HTTP %s. %s" % (status, hints.get(status, "Request failed."))) from None
        except (urllib.error.URLError, TimeoutError):
            raise JevError("Could not reach TypeSafe API or request timed out.") from None
        except (ValueError, UnicodeError):
            raise JevError("API returned invalid JSON.") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="Text to evaluate")
    parser.add_argument("--question", required=True)
    parser.add_argument("--option", action="append", required=True, help="id:description")
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--key-file", type=Path, default=KEY_FILE)
    parser.add_argument("--dry-run", action="store_true", help="Print request without API access")
    args = parser.parse_args()
    criteria = {}
    for option in args.option:
        label, separator, description = option.partition(":")
        if not separator or not label.strip() or not description.strip() or label in criteria:
            parser.error("Each option must have a unique nonempty id and description: id:description")
        criteria[label] = description
    if len(criteria) < 2 or not args.state.strip() or not args.question.strip():
        parser.error("Provide state, question and at least two options.")
    questions = {"decision": {"type": "choice", "instructions": args.question, "criteria": criteria}}
    try:
        result = ({"model": args.model, "state": args.state, "questions": questions}
                  if args.dry_run else evaluate(args.state, questions, args.model, args.key_file))
    except (JevError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
