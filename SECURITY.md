# Sophia Security Policy

## Contact & Disclosure
- **Report vulnerabilities:** security@sophia.ai (preferred) or open a “Security” issue in the private tracker.
- **Target response time:** acknowledge within 2 business days, provide a remediation plan within 7 business days.
- **Coordinated disclosure:** please allow us time to release a fix before public disclosure. We will credit researchers unless anonymity is requested.

## Supported Versions
| Version | Supported | Notes |
| --- | --- | --- |
| `main` branch | ✅ | Actively maintained, security fixes land here first. |
| Tagged releases ≤ 30 days old | ✅ | Receive backported fixes if practical. |
| Older branches / forks | ⚠️ | Best-effort support only; please upgrade to the latest release. |

## Dependency Management
- Weekly Dependabot checks (configured via GitHub) keep Python packages current. Pull requests with security updates are triaged as High priority.
- CI (`.github/workflows/ci.yml`) locks dependencies via `uv.lock`, installs them with `uv sync`, and executes `uv run pytest` to detect regressions.
- Production images are rebuilt at least monthly to pick up OS-level patches.

## Vulnerability Handling
1. **Intake & triage:** validate the report, assess severity (CVSS reference), and assign an owner.
2. **Patch development:** create a fix in a protected branch; add regression tests whenever feasible.
3. **Verification:** run full CI and targeted integration tests (consent flows, Supabase writes, LangGraph pipelines).
4. **Release:** merge to `main`, deploy to staging, then production once verified. Communicate remediation to the reporter.
5. **Postmortem:** document lessons learned if severity ≥ High or customer data was at risk.

## Configuration Hardening
- The backend aborts startup when mandatory environment variables are missing (`validate_settings`), ensuring secure-by-default deployments.
- API access requires keys in all environments; middleware blocks requests without a valid `Authorization: Bearer` header.
- Supabase defaults disallow the zero UUID; RLS policies (planned for Phase 1) will further isolate tenant data.

## Awareness & Training
- Backend contributors are expected to review this policy during onboarding.
- Quarterly tabletop exercises simulate credential leakage and AI provider outages.
- Any new third-party service integration must pass a lightweight security review (data handling, auth, logging).

## Known Issues
- No unresolved High or Medium vulnerabilities as of 2025-01-07.
- Remaining tasks tracked in `docs/PHASE_PLAN.md` (e.g., automated vulnerability scanning and cold-start optimization).
