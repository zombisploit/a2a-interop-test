# A2A Interoperability Test Suite for Ferminux

Runnable test suite (Python) that exercises Ferminux A2A endpoints:

- `GET https://ferminux.net/a/<slug>/.well-known/agent.json` (Agent Card discovery)
- `POST https://ferminux.net/a/<slug>/a2a` with JSON-RPC `message/send`

Covers:

1. **x402-paid path** — bare `message/send` returns HTTP 402 / PaymentRequired (x402-ferminux voucher scheme)
2. **Pre-funded escrow path** — `params.metadata.jobId` lets the call proceed without a PAYMENT header when a valid on-chain job exists

Also probes which official / community A2A client libraries can talk to Ferminux *unchanged* (or with minimal metadata injection).

## Quick start

```bash
pip install -r requirements.txt
python test_suite.py --slug toolbox --job-id 1
# or
python test_suite.py --slug toolbox
