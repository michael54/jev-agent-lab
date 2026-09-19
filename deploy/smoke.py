"""Run real authenticated requests from outside the Pod and save measured results."""
import json
import pathlib
import sys
import time
import urllib.request
import urllib.error

base, key_file, output_file = sys.argv[1:]
key = pathlib.Path(key_file).read_text().strip()
cases = [
    ("route-en", "Please find the current weather in Tokyo.", "Which tool should be used?", [("weather", "Look up live weather"), ("calculator", "Perform arithmetic"), ("files", "Read local files")], "weather"),
    ("route-zh", "请查询东京现在的天气。", "应该选择哪个工具？", [("weather", "查询实时天气"), ("calculator", "数学计算"), ("files", "读取本地文件")], "weather"),
    ("retry-en", "HTTP 429 Too Many Requests. Retry-After: 5 seconds.", "What should the agent do next?", [("retry", "Wait five seconds and retry"), ("done", "Mark the task complete"), ("delete", "Delete local files")], "retry"),
    ("retry-zh", "请求返回 HTTP 429，服务器要求5秒后重试。", "下一步应该怎么做？", [("retry", "等待5秒后重试"), ("done", "报告任务成功"), ("delete", "删除本地文件")], "retry"),
    ("evidence-en", "A test suite was not run. Only the source code was edited.", "Does this establish that all tests passed?", [("yes", "Yes, tests passed"), ("no", "No, passing tests are not established")], "no"),
    ("evidence-zh", "只修改了源代码，没有运行任何测试。", "能否声称全部测试已通过？", [("yes", "可以，已有测试通过的证据"), ("no", "不可以，没有运行测试")], "no"),
]
def request(payload, token=None):
    headers = {"Content-Type": "application/json", "User-Agent": "jev-experiment/0.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + "/v1/decide", json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)
results = []
for name, state, question, options, expected in cases:
    payload = {"id": name, "state": state, "question": question,
               "options": [{"id": i, "description": d} for i, d in options]}
    started = time.perf_counter()
    result = request(payload, key)
    results.append({"expected": expected, "correct": result["choice"] == expected,
                    "http_seconds": time.perf_counter() - started, **result})
    print(name, result["choice"], round(results[-1]["http_seconds"], 3), flush=True)
try:
    request(payload)
    raise AssertionError("Unauthenticated request was accepted")
except urllib.error.HTTPError as error:
    assert error.code == 401, error.code
duplicate = dict(payload, options=[{"id":"same","description":"A"},{"id":"same","description":"B"}])
try:
    request(duplicate, key)
    raise AssertionError("Duplicate options were accepted")
except urllib.error.HTTPError as error:
    assert error.code == 422, error.code
report = {"base_url": base, "correct": sum(x["correct"] for x in results),
          "count": len(results), "auth_rejection": 401, "duplicate_rejection": 422,
          "note": "Handcrafted smoke cases, not an unbiased quality benchmark.", "results": results}
with open(output_file, "x") as file:
    json.dump(report, file, ensure_ascii=False, indent=2)
print("Saved", output_file)
