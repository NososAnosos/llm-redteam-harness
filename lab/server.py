#!/usr/bin/env python3
"""Red team lab: local web UI over the eval harness. Standard library only. Binds the Tailscale interface when available (localhost fallback).

Read-only with respect to the harness: never writes to results/ or any transcript.
Live runs are ephemeral and returned as JSON.
"""
import glob
import html
import json
import os
import subprocess
import sys
import time
import types
import urllib.request

sys.dont_write_bytecode = True  # don't drop __pycache__ into the parent dir
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import run_eval  # noqa: E402  (reuse run_case / load_cases)
from scoring import score_case  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

def _bind_host():
    """Bind the Tailscale interface when available so the lab is reachable from
    Kristopher's other devices on the tailnet; fall back to localhost."""
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True,
                             text=True, timeout=5).stdout.strip().split()
        if out:
            return out[0]
    except Exception:
        pass
    return "127.0.0.1"


HOST, PORT = _bind_host(), 8471
CASE_DIR = os.path.join(ROOT, "cases")
RESULTS_DIR = os.path.join(ROOT, "results")
QWEN_KEY_FILE = "/home/nosos/.hermes/runtimes/llamacpp/.api_key"

TARGETS = {
    "gemma": {"base_url": "http://127.0.0.1:11434/v1", "model": "gemma3:4b"},
    "qwen": {"base_url": "http://127.0.0.1:18434/v1", "model": "Qwen3-8B-Q4_K_M",
             "key_file": QWEN_KEY_FILE, "chat_template_kwargs": {"enable_thinking": False}},
}
# Serialize live runs: the backing servers are single-slot.
RUN_LOCK = __import__("threading").Lock()


# ---------- data ----------
def all_cases():
    return run_eval.load_cases(CASE_DIR)


def get_case(case_id):
    for c in all_cases():
        if c["id"] == case_id:
            return c
    return None


def iter_runs():
    """Yield (run_dir_name, record) for every line of every results/*/transcript.jsonl."""
    for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "*", "transcript.jsonl"))):
        run = os.path.basename(os.path.dirname(path))
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        yield run, json.loads(line)
                    except ValueError:
                        continue


def run_summaries():
    runs = {}
    for run, rec in iter_runs():
        r = runs.setdefault(run, {"model": rec.get("model"), "pass": 0, "fail": 0, "ambiguous": 0})
        v = (rec.get("score") or {}).get("verdict", "ambiguous")
        r[v if v in ("pass", "fail", "ambiguous") else "ambiguous"] += 1
    return runs


def target_args(name):
    t = TARGETS[name]
    key = None
    if t.get("key_file"):
        with open(t["key_file"]) as f:
            key = f.read().strip()
    ctk = t.get("chat_template_kwargs")
    return types.SimpleNamespace(
        base_url=t["base_url"], model=t["model"], api_key=key, temperature=0.0, top_p=1.0,
        max_tokens=None, timeout=300, chat_template_kwargs=json.dumps(ctk) if ctk else None)


def probe_target(name):
    try:
        a = target_args(name)
        headers = {"Authorization": f"Bearer {a.api_key}"} if a.api_key else {}
        req = urllib.request.Request(a.base_url.rstrip("/") + "/models", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def live_run(case_id, target, mutated_turn=None):
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}")
    case = get_case(case_id)
    if case is None:
        raise KeyError(f"unknown case {case_id!r}")
    case = json.loads(json.dumps(case))  # deep copy; never mutate the loaded case
    if mutated_turn is not None:
        if not isinstance(mutated_turn, str):
            raise ValueError("mutated_turn must be a string")
        for t in reversed(case["turns"]):
            if t["role"] == "user":
                t["content"] = mutated_turn
                break
    args = target_args(target)
    t0 = time.monotonic()
    error, replies, convo = None, [], run_eval.build_messages(case)
    with RUN_LOCK:
        try:
            replies, _params, convo = run_eval.run_case(args, case)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    latency = round(time.monotonic() - t0, 3)
    response = replies[-1] if replies else ""
    score = score_case(case, response, error)
    return {"case_id": case_id, "target": target, "model": args.model,
            "mutated": mutated_turn is not None, "conversation": convo, "response": response,
            "verdict": score["verdict"], "classification": score.get("classification"),
            "reasons": score["reasons"], "notes": score.get("notes", []),
            "latency_s": latency, "error": error}


# ---------- html ----------
CSS = """
:root{--bg:#0f1417;--panel:#171e22;--line:#27323a;--fg:#d6dde1;--dim:#8a979f;--accent:#2aa198}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 20px 60px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1,h2,h3{font-weight:600}h1{color:var(--accent);margin-top:0}
h2{border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:32px}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:500}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 16px;margin:12px 0}
pre{white-space:pre-wrap;word-wrap:break-word;background:#0b0f11;border:1px solid var(--line);
 border-radius:4px;padding:10px;margin:6px 0;font:13px/1.45 ui-monospace,monospace}
.role{color:var(--accent);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;border:1px solid}
.pass{color:#6fcf7f;border-color:#6fcf7f}.fail{color:#ff6b6b;border-color:#ff6b6b}
.ambiguous{color:#e0b84a;border-color:#e0b84a}
.dim{color:var(--dim)}
textarea{width:100%;min-height:110px;background:#0b0f11;color:var(--fg);border:1px solid var(--line);
 border-radius:4px;padding:10px;font:13px ui-monospace,monospace}
button,select{background:var(--panel);color:var(--fg);border:1px solid var(--accent);border-radius:4px;
 padding:6px 14px;font:inherit}
button{background:var(--accent);color:#06201e;cursor:pointer;font-weight:600}
button:disabled{opacity:.5;cursor:wait}
"""


def page(title, body):
    return (f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style><main>{body}</main>")


def esc(x):
    return html.escape("" if x is None else str(x))


def pill(v):
    return f'<span class="pill {esc(v)}">{esc(v)}</span>'


def index_page():
    cases = all_cases()
    cats = {}
    for c in cases:
        cats.setdefault(c["category"], []).append(c)
    rows = "".join(
        f"<tr><td>{esc(cat)}</td><td>{len(cs)}</td><td class=dim>"
        + ", ".join(f'<a href="/case?id={esc(c["id"])}">{esc(c["id"])}</a>' for c in cs)
        + "</td></tr>" for cat, cs in sorted(cats.items()))
    runs = run_summaries()
    rrows = ""
    for run, r in runs.items():
        n = r["pass"] + r["fail"] + r["ambiguous"]
        rate = f"{100 * r['pass'] / n:.1f}%" if n else "-"
        rrows += (f"<tr><td>{esc(run)}</td><td>{esc(r['model'])}</td><td>{n}</td><td>{r['pass']}</td>"
                  f"<td>{r['fail']}</td><td>{r['ambiguous']}</td><td>{rate}</td></tr>")
    body = (f"<h1>Red Team Lab</h1><p class=dim>{len(cases)} cases in {len(cats)} categories. "
            f"Live runs are ephemeral; nothing is written to results/.</p>"
            f"<h2>Categories</h2><table><tr><th>Category</th><th>Cases</th><th>IDs</th></tr>{rows}</table>"
            f"<h2>Model runs</h2><table><tr><th>Run</th><th>Model</th><th>Cases</th><th>Pass</th>"
            f"<th>Fail</th><th>Ambiguous</th><th>Pass rate</th></tr>"
            f"{rrows or '<tr><td colspan=7 class=dim>No runs found</td></tr>'}</table>")
    return page("Red Team Lab", body)


def case_page(case):
    turns = "".join(f'<div class=role>{esc(t["role"])}</div><pre>{esc(t["content"])}</pre>'
                    for t in case["turns"])
    final_user = next((t["content"] for t in reversed(case["turns"]) if t["role"] == "user"), "")
    runs = ""
    for run, rec in iter_runs():
        if rec.get("case", {}).get("id") != case["id"]:
            continue
        sc = rec.get("score") or {}
        resp = rec.get("response") or ""
        excerpt = resp[:600] + ("…" if len(resp) > 600 else "")
        runs += (f'<div class=card><b>{esc(run)}</b> <span class=dim>{esc(rec.get("model"))}</span> '
                 f'{pill(sc.get("verdict"))}<ul>'
                 + "".join(f"<li>{esc(r)}</li>" for r in sc.get("reasons", []))
                 + f'</ul><pre>{esc(excerpt)}</pre></div>')
    meta = {k: case.get(k) for k in ("canary", "must_not_contain", "must_contain_any")}
    body = (f'<a href="/">&larr; index</a><h1>{esc(case["id"])}: {esc(case["name"])}</h1>'
            f'<p><span class=dim>{esc(case["category"])}</span> · expects <b>{esc(case["expect"])}</b> · '
            f'<span class=dim>{esc(case["provenance"])}</span></p>'
            f'<h2>System prompt</h2><pre>{esc(case["system"]) if case["system"] else "(none)"}</pre>'
            f'<h2>Turns</h2>{turns}'
            f'<h2>Scoring markers</h2><pre>{esc(json.dumps(meta, indent=1))}</pre>'
            f'<h2>Existing runs</h2>{runs or "<p class=dim>No recorded runs for this case.</p>"}'
            f'<h2>Run live</h2><div class=card>'
            f'<p class=dim>Edit the final user turn to mutate the attack, then rerun. '
            f'Temperature 0; results are not saved.</p>'
            f'<label>Target <select id=target></select></label>'
            f'<p><textarea id=turn>{esc(final_user)}</textarea></p>'
            f'<button id=run>Run</button> <span id=status class=dim></span></div>'
            f'<div id=out></div>'
            f'<script>const CASE_ID={json.dumps(case["id"])};{JS}</script>')
    return page(case["id"], body)


JS = r"""
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
fetch('/targets').then(r=>r.json()).then(t=>{
  $('target').innerHTML=Object.entries(t).map(([k,v])=>
    `<option value="${k}"${v.up?'':' disabled'}>${k} (${esc(v.model)})${v.up?'':' - down'}</option>`).join('');
});
$('run').onclick=async()=>{
  const b=$('run');b.disabled=true;$('status').textContent='running...';$('out').innerHTML='';
  try{
    const r=await fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({case_id:CASE_ID,target:$('target').value,mutated_turn:$('turn').value})});
    const d=await r.json();
    if(!r.ok){$('out').innerHTML=`<div class=card>Error: ${esc(d.error)}</div>`;return}
    $('out').innerHTML='<h2>Result</h2><div class=card>'+
      `<span class="pill ${esc(d.verdict)}">${esc(d.verdict)}</span> `+
      `<span class=dim>${esc(d.model)} · ${d.latency_s}s · classified ${esc(d.classification)}</span>`+
      (d.error?`<p class=fail>${esc(d.error)}</p>`:'')+
      '<ul>'+d.reasons.concat(d.notes||[]).map(x=>`<li>${esc(x)}</li>`).join('')+'</ul></div>'+
      d.conversation.map(m=>`<div class=role>${esc(m.role)}</div><pre>${esc(m.content)}</pre>`).join('');
  }catch(e){$('out').innerHTML=`<div class=card>Request failed: ${esc(e)}</div>`}
  finally{b.disabled=false;$('status').textContent=''}
};
"""


# ---------- http ----------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json")

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        try:
            if u.path == "/":
                self._send(200, index_page())
            elif u.path == "/case":
                case = get_case((parse_qs(u.query).get("id") or [""])[0])
                if case is None:
                    self._send(404, page("Not found", "<h1>Unknown case id</h1><a href='/'>back</a>"))
                else:
                    self._send(200, case_page(case))
            elif u.path == "/targets":
                self._json(200, {k: {"model": t["model"], "up": probe_target(k)}
                                 for k, t in TARGETS.items()})
            else:
                self._send(404, page("Not found", "<h1>Not found</h1>"))
        except Exception as e:
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if self.path != "/run":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            result = live_run(req.get("case_id"), req.get("target"), req.get("mutated_turn"))
            self._json(200, result)
        except (KeyError, ValueError) as e:
            self._json(400, {"error": str(e)})
        except Exception as e:
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *a):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % a))


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Red team lab on http://{HOST}:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
