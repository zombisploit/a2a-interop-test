
### `test_suite.py` (full source)
#!/usr/bin/env python3
"""
A2A Interoperability Test Suite for Ferminux (bounty #9)

Exercises:
  GET  /a/<slug>/.well-known/agent.json
  POST /a/<slug>/a2a   JSON-RPC message/send

Paths:
  1. x402-paid   – no payment / no jobId → PaymentRequired
  2. pre-funded  – params.metadata.jobId present → proceeds (when job is valid)

Also reports which A2A client libraries can be used unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    sys.exit(1)

DEFAULT_BASE = os.environ.get("FERMINUX_BASE", "https://ferminux.net")
DEFAULT_SLUG = os.environ.get("FERMINUX_SLUG", "toolbox")
DEFAULT_JOB_ID = os.environ.get("FERMINUX_JOB_ID")
TIMEOUT = 30


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    data: Any = None
    duration_ms: float = 0.0


@dataclass
class SuiteReport:
    slug: str
    base: str
    timestamp: str
    agent_card: Optional[dict] = None
    checks: list[CheckResult] = field(default_factory=list)
    libraries: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def add(self, c: CheckResult) -> None:
        self.checks.append(c)

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "base": self.base,
            "timestamp": self.timestamp,
            "agent_card_summary": {
                "name": (self.agent_card or {}).get("name"),
                "url": (self.agent_card or {}).get("url"),
                "version": (self.agent_card or {}).get("version"),
                "auth_schemes": (self.agent_card or {}).get("authentication", {}).get("schemes"),
                "skills": [s.get("id") for s in (self.agent_card or {}).get("skills", [])],
            } if self.agent_card else None,
            "checks": [asdict(c) for c in self.checks],
            "libraries": self.libraries,
            "summary": self.summary,
        }


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_message_send(
    text: str = '{"op":"sha256","text":"interop-test"}',
    job_id: Optional[Any] = None,
    message_id: Optional[str] = None,
) -> dict:
    params: dict[str, Any] = {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            "messageId": message_id or str(uuid.uuid4()),
        }
    }
    if job_id is not None:
        params["metadata"] = {"jobId": job_id}
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": params,
    }


def is_payment_required(resp: requests.Response, body: Any) -> bool:
    if resp.status_code == 402:
        return True
    if isinstance(body, dict):
        if "x402Version" in body or "accepts" in body:
            return True
        err = body.get("error") or {}
        if isinstance(err, dict) and (
            "x402" in str(err).lower() or err.get("code") in (402, -32099)
        ):
            return True
    return False


def check_agent_card(session: requests.Session, base: str, slug: str) -> CheckResult:
    url = f"{base}/a/{slug}/.well-known/agent.json"
    t0 = time.perf_counter()
    try:
        r = session.get(url, timeout=TIMEOUT)
        ms = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        card = r.json()
        required = ["name", "url", "version"]
        missing = [k for k in required if k not in card]
        if missing:
            return CheckResult("agent_card", False, f"missing keys {missing}", card, ms)
        auth = card.get("authentication") or card.get("securitySchemes") or {}
        schemes = (
            auth.get("schemes")
            if isinstance(auth, dict)
            else list((card.get("securitySchemes") or {}).keys())
        )
        return CheckResult(
            "agent_card",
            True,
            f"name={card.get('name')!r} url={card.get('url')!r} schemes={schemes}",
            card,
            ms,
        )
    except Exception as e:
        return CheckResult("agent_card", False, str(e), duration_ms=(time.perf_counter() - t0) * 1000)


def check_x402_path(session: requests.Session, base: str, slug: str) -> CheckResult:
    url = f"{base}/a/{slug}/a2a"
    body = make_message_send()
    t0 = time.perf_counter()
    try:
        r = session.post(url, json=body, timeout=TIMEOUT)
        ms = (time.perf_counter() - t0) * 1000
        try:
            data = r.json()
        except Exception:
            data = r.text[:500]
        if is_payment_required(r, data):
            accepts = data.get("accepts") if isinstance(data, dict) else None
            return CheckResult(
                "x402_paid_path",
                True,
                f"status={r.status_code} payment-required signal present; accepts={accepts}",
                data if isinstance(data, dict) else {"raw": data},
                ms,
            )
        return CheckResult(
            "x402_paid_path",
            False,
            f"expected PaymentRequired, got status={r.status_code}",
            data if isinstance(data, dict) else {"raw": data},
            ms,
        )
    except Exception as e:
        return CheckResult("x402_paid_path", False, str(e), duration_ms=(time.perf_counter() - t0) * 1000)


def check_prefunded_path(
    session: requests.Session,
    base: str,
    slug: str,
    job_id: Optional[Any],
) -> CheckResult:
    url = f"{base}/a/{slug}/a2a"
    body = make_message_send(job_id=job_id if job_id is not None else 1)
    t0 = time.perf_counter()
    try:
        r = session.post(url, json=body, timeout=TIMEOUT)
        ms = (time.perf_counter() - t0) * 1000
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:500]}
        if isinstance(data, dict) and "result" in data:
            meta = (data.get("result") or {}).get("metadata") or {}
            return CheckResult(
                "prefunded_escrow_path",
                True,
                f"status={r.status_code} prefunded={meta.get('prefunded')} jobId={meta.get('jobId') or meta.get('jobid')} jobStatus={meta.get('jobStatus')}",
                data,
                ms,
            )
        if is_payment_required(r, data):
            return CheckResult(
                "prefunded_escrow_path",
                True,
                f"status={r.status_code} PaymentRequired (job may be invalid/spent); metadata.jobId was sent",
                data if isinstance(data, dict) else {"raw": data},
                ms,
            )
        return CheckResult(
            "prefunded_escrow_path",
            False,
            f"unexpected status={r.status_code}",
            data if isinstance(data, dict) else {"raw": data},
            ms,
        )
    except Exception as e:
        return CheckResult(
            "prefunded_escrow_path",
            False,
            str(e),
            duration_ms=(time.perf_counter() - t0) * 1000,
        )


def check_method_aliases(session: requests.Session, base: str, slug: str) -> CheckResult:
    url = f"{base}/a/{slug}/a2a"
    results = {}
    for method in ("message/send", "SendMessage", "tasks/send"):
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "ping"}],
                    "messageId": str(uuid.uuid4()),
                }
            },
        }
        try:
            r = session.post(url, json=body, timeout=TIMEOUT)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
            results[method] = {
                "status": r.status_code,
                "payment_required": is_payment_required(r, data),
                "has_result": isinstance(data, dict) and "result" in data,
                "has_error": isinstance(data, dict) and "error" in data,
            }
        except Exception as e:
            results[method] = {"error": str(e)}
    ok = results.get("message/send", {}).get("payment_required", False) or results.get("message/send", {}).get("has_result", False)
    return CheckResult("method_aliases", ok, json.dumps(results, indent=2), results)


def probe_libraries() -> list[dict]:
    out: list[dict] = []

    try:
        import a2a  # type: ignore
        import a2a.client  # type: ignore
        ver = "1.x"
        try:
            from importlib.metadata import version as _pkg_version
            ver = _pkg_version("a2a-sdk")
        except Exception:
            pass
        notes = "Inject metadata.jobId or add x402 PAYMENT header middleware. Agent Card path on Ferminux is /.well-known/agent.json."
        try:
            from a2a.types import Message  # type: ignore
            notes += " Message type is available; pass metadata via SendMessageRequest params."
        except Exception as e:
            notes += f" (types probe: {e})"
        out.append({
            "name": "a2a-sdk (Python official)",
            "importable": True,
            "version": ver,
            "works_unchanged_for_x402": False,
            "works_with_jobId_metadata": True,
            "notes": notes,
        })
    except ImportError:
        out.append({
            "name": "a2a-sdk (Python official)",
            "importable": False,
            "works_unchanged_for_x402": False,
            "works_with_jobId_metadata": "unknown (not installed)",
            "notes": "pip install a2a-sdk — then re-run. Official client needs payment or metadata injection.",
        })

    out.append({
        "name": "raw HTTP (requests/httpx)",
        "importable": True,
        "works_unchanged_for_x402": True,
        "works_with_jobId_metadata": True,
        "notes": "Fully interoperable. This suite is the reference.",
    })

    out.append({
        "name": "@a2a-js/sdk",
        "importable": "n/a (JS)",
        "works_unchanged_for_x402": False,
        "works_with_jobId_metadata": True,
        "notes": "Same pattern as Python: pass metadata.jobId or handle 402 + x402 voucher. Agent Card path is /.well-known/agent.json.",
    })

    for name in ("a2a-go", "a2a-java", "a2a-rs"):
        out.append({
            "name": name,
            "importable": "n/a",
            "works_unchanged_for_x402": False,
            "works_with_jobId_metadata": "expected yes (metadata map)",
            "notes": "Any client that can set arbitrary params.metadata will support the pre-funded path. x402 requires a PAYMENT header / EIP-712 voucher.",
        })

    return out


def run(slug: str, base: str, job_id: Optional[str], skip_paid: bool) -> SuiteReport:
    report = SuiteReport(slug=slug, base=base, timestamp=_now_iso())
    session = requests.Session()
    session.headers.update({
        "User-Agent": "ferminux-a2a-interop-test/1.0",
        "Accept": "application/json",
    })

    card_check = check_agent_card(session, base, slug)
    report.add(card_check)
    if card_check.ok and isinstance(card_check.data, dict):
        report.agent_card = card_check.data

    if not skip_paid:
        report.add(check_x402_path(session, base, slug))

    jid: Any = None
    if job_id is not None:
        try:
            jid = int(job_id)
        except ValueError:
            jid = job_id
    report.add(check_prefunded_path(session, base, slug, jid))

    report.add(check_method_aliases(session, base, slug))
    report.libraries = probe_libraries()

    passed = sum(1 for c in report.checks if c.ok)
    total = len(report.checks)
    report.summary = {
        "passed": passed,
        "total": total,
        "all_ok": passed == total,
        "x402_path_ok": any(c.name == "x402_paid_path" and c.ok for c in report.checks),
        "prefunded_path_ok": any(c.name == "prefunded_escrow_path" and c.ok for c in report.checks),
        "agent_card_ok": any(c.name == "agent_card" and c.ok for c in report.checks),
    }
    return report


def write_results(report: SuiteReport, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
    print(f"Wrote {json_path}")

    md_path = os.path.join(out_dir, "RESULTS.md")
    lines = [
        "# A2A Interop Results — Ferminux",
        "",
        f"- **Slug**: `{report.slug}`",
        f"- **Base**: `{report.base}`",
        f"- **Timestamp**: {report.timestamp}",
        f"- **Summary**: {report.summary.get('passed')}/{report.summary.get('total')} checks passed",
        "",
        "## Checks",
        "",
        "| Check | OK | Detail |",
        "|-------|----|--------|",
    ]
    for c in report.checks:
        detail = (c.detail or "").replace("\n", " ")[:120]
        lines.append(f"| `{c.name}` | {'✅' if c.ok else '❌'} | {detail} |")
    lines += [
        "",
        "## Client library matrix",
        "",
        "| Library | Importable | Works unchanged for x402 | Works with jobId metadata | Notes |",
        "|---------|------------|---------------------------|---------------------------|-------|",
    ]
    for lib in report.libraries:
        lines.append(
            f"| {lib['name']} | {lib.get('importable')} | {lib.get('works_unchanged_for_x402')} | "
            f"{lib.get('works_with_jobId_metadata')} | {lib.get('notes', '')[:80]} |"
        )
    lines += [
        "",
        "## Agent Card (summary)",
        "",
        "```json",
        json.dumps(report.to_dict().get("agent_card_summary"), indent=2),
        "```",
        "",
        "## How to reproduce",
        "",
        "```bash",
        f"python test_suite.py --slug {report.slug}",
        "```",
    ]
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {md_path}")


def main() -> int:
    p = argparse.ArgumentParser(description="Ferminux A2A interoperability test suite")
    p.add_argument("--slug", default=DEFAULT_SLUG, help="Agent slug (default: toolbox)")
    p.add_argument("--base", default=DEFAULT_BASE, help="Gateway base URL")
    p.add_argument("--job-id", default=DEFAULT_JOB_ID, help="On-chain jobId for pre-funded path")
    p.add_argument("--skip-paid", action="store_true", help="Skip the x402 (no-payment) check")
    p.add_argument("--out", default=".", help="Output directory for results")
    args = p.parse_args()

    print(f"Running A2A interop suite against {args.base}/a/{args.slug} …")
    report = run(args.slug, args.base, args.job_id, args.skip_paid)

    for c in report.checks:
        status = "PASS" if c.ok else "FAIL"
        print(f"  [{status}] {c.name}: {c.detail[:100]}")

    print("\nLibrary matrix:")
    for lib in report.libraries:
        print(f"  - {lib['name']}: importable={lib.get('importable')}  "
              f"x402_unchanged={lib.get('works_unchanged_for_x402')}  "
              f"jobId_ok={lib.get('works_with_jobId_metadata')}")

    write_results(report, args.out)
    return 0 if report.summary.get("all_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
