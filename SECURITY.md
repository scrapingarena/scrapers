# Security policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting: go to the
[Security tab](https://github.com/scrapingarena/scrapers/security) of this
repository and choose **Report a vulnerability**. That opens a private advisory
visible only to maintainers.

Please include what the issue is, how to reproduce it, what an attacker could
achieve, and the affected version or commit.

We aim to acknowledge within a few days. Please give us reasonable time to ship
a fix before disclosing publicly.

## What's in scope

This repository runs untrusted web content through scraping engines and an LLM
validator, and holds proxy and API credentials in CI. Most relevant:

- **Credential leakage** — proxy credentials or API keys reaching reports,
  logs, error messages, artifacts, or committed files. Reports are published to
  a public repository, so anything that reaches one is public.
- **Prompt injection** — scraped page content steering the validator into
  wrong verdicts. The validator treats page content as untrusted evidence and
  instructs the model to ignore instructions found in it. Bypasses are in scope.
- **Result tampering** — any path by which an adapter or contributed code could
  influence its own score, or corrupt another scraper's shard.
- **CI/supply chain** — workflow injection, secret exfiltration from a pull
  request, or dependency substitution.

## What's not in scope

- Vulnerabilities in the scraping libraries, browsers, or services this project
  benchmarks. Report those upstream — adapter homepages are in
  [`docs/scrapers.md`](docs/scrapers.md). If the *adapter* mishandles a library
  safely, that is in scope.
- Anti-bot systems on benchmark target sites. Not our software.
- Rate limits or costs on your own OpenAI or proxy account.

## Notes for contributors

- Never commit credentials. Use GitHub Actions secrets and reference them from
  the workflow.
- Extend `ProxySettings.redact()` when adding a provider whose username format
  embeds routing options, so it can't survive into an error message.
- Raw HTML and response headers are deliberately excluded from persisted
  reports. Don't add them back — pages can contain copyrighted content, session
  data, and identifiers.
