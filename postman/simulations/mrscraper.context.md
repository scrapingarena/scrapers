# MrScraper local simulation

Created 2026-10-28 from synthetic fixtures matching the supplied REST reference
(20 October 2026). Published owner mocks were not searched: the Postman CLI is
signed out. The fixture contract is in `../mocks/mrscraper/default.js`.

## Purpose

Exercise the actual Python HTTP client and benchmark adapter against local
Account, scraperAPI, and webSearch responses without live target requests.

## Execution

1. `postman simulation run postman/simulations/mrscraper.sim.yaml --port auto --no-history --output ndjson`
2. Read the member address from the `listening` event.
3. `uv run python scripts/smoke_mrscraper.py --simulation-url <member-address>`
4. Check the `request` events for all three routes and the deliberate HTTP 401.
5. Stop the simulation with Ctrl-C.

## Assumptions

- The smoke command uses only synthetic keys and rejects non-loopback hosts.
  It never needs production credentials. (observed 2026-10-28)
- Fixtures establish request wiring and response parsing, not live page quality,
  image validity, proxy connectivity, or vendor performance. The screenshot is
  a non-decodable placeholder; the real API supplies a base64 JPEG. (reasoned
  2026-10-28, the fixture handler)
- API HTTP status and target `X-Status-Code` are separate. The benchmark uses
  the latter. (supplied reference; observed 2026-10-28)

## Observations

<!-- begin:observations -->
2026-10-28: the MrScraper member served all three routes, combined-output fetch,
the adapter fetch, and the invalid-key check. No member stayed silent. The
smoke command passed; the HTTP log confirms the runner-facing fetch sends
`maxRetries=0`, rendering enabled, and direct proxy routing disabled.
<!-- end:observations -->
