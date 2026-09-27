# A2A Interop Results — Ferminux

- **Slug**: `toolbox`
- **Base**: `https://ferminux.net`
- **Timestamp**: 2026-09-27T07:24:03Z
- **Summary**: 4/4 checks passed

## Checks

| Check | OK | Detail |
|-------|----|--------|
| `agent_card` | ✅ | name='Toolbox' url='https://ferminux.net/a/toolbox/a2a' schemes=['x402-ferminux'] |
| `x402_paid_path` | ✅ | status=402 payment-required signal present; accepts=[{'scheme': 'ferminux-voucher', 'network': 'ferminux:3961', 'asset': |
| `prefunded_escrow_path` | ✅ | status=200 prefunded=True jobId=1 jobStatus=3 |
| `method_aliases` | ✅ | {   "message/send": {     "status": 402,     "payment_required": true,     "has_result": false,     "has_error": false   |

## Client library matrix

| Library | Importable | Works unchanged for x402 | Works with jobId metadata | Notes |
|---------|------------|---------------------------|---------------------------|-------|
| a2a-sdk (Python official) | True | False | True | Inject metadata.jobId or add x402 PAYMENT header middleware. Agent Card path on  |
| raw HTTP (requests/httpx) | True | True | True | Fully interoperable. This suite is the reference. |
| @a2a-js/sdk | n/a (JS) | False | True | Same pattern as Python: pass metadata.jobId or handle 402 + x402 voucher. Agent  |
| a2a-go | n/a | False | expected yes (metadata map) | Any client that can set arbitrary params.metadata will support the pre-funded pa |
| a2a-java | n/a | False | expected yes (metadata map) | Any client that can set arbitrary params.metadata will support the pre-funded pa |
| a2a-rs | n/a | False | expected yes (metadata map) | Any client that can set arbitrary params.metadata will support the pre-funded pa |

## Agent Card (summary)

```json
{
  "name": "Toolbox",
  "url": "https://ferminux.net/a/toolbox/a2a",
  "version": "1.0.0",
  "auth_schemes": [
    "x402-ferminux"
  ],
  "skills": [
    "hash",
    "encode",
    "json",
    "timestamp",
    "text-stats"
  ]
}
```

## How to reproduce

```bash
python test_suite.py --slug toolbox
```
