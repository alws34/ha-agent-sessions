# OpenSSF / supply-chain checklist

What the repository provides, and what the maintainer switches on in GitHub or on external sites.

## In the repository

| Area | Where |
|---|---|
| All actions pinned by commit SHA, `contents: read` by default, write scopes per job, no `pull_request_target`, no `github.event.*` in `run:`, checkout without persisted credentials | `.github/workflows/*` |
| Pinned test/lint tooling | `requirements_test.txt` |
| Dependency updates (pip, actions; monthly, grouped) | `.github/dependabot.yml` |
| CI: HACS validation, hassfest, ruff, shellcheck, tests with coverage | `validate.yml` |
| SAST: CodeQL (Python, JavaScript, Actions); SonarQube Cloud when `SONAR_TOKEN` is set | `codeql.yml`, `validate.yml`, `sonar-project.properties` |
| Scorecard with published results and SARIF upload | `scorecard.yml` |
| Releases from tags: version and checksum checks, assets with SLSA provenance | `release.yml` |
| Server code pinned by SHA-256 in the integration | `const.py`, `agent/install.sh` |
| Security policy, threat model, private reporting | `SECURITY.md`, `docs/threat-model.md` |
| Contribution guide, code of conduct, code owners, issue/PR templates | `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.github/` |
| OSI license | `LICENSE` (MIT) |

## Manual steps

1. **Private vulnerability reporting**: Settings → Code security → enable it (`SECURITY.md`, the issue forms and
   `CODE_OF_CONDUCT.md` point there).
2. **Secret scanning + push protection**, **Dependabot alerts** and **Dependabot security updates**: same page.
3. **Code scanning**: if CodeQL "default setup" is on, switch it off so it doesn't conflict with `codeql.yml`.
4. **Ruleset for `main`**: block force pushes and deletions; require a pull request; require the checks
   `HACS validation`, `hassfest`, `Lint and test`, and the three `Analyze (...)` jobs.
5. **Workflow permissions**: Settings → Actions → General → *Read repository contents*; leave "Allow GitHub Actions
   to create and approve pull requests" unchecked.
6. **SonarQube Cloud** (optional): import the repository on <https://sonarcloud.io>, set the organization and project
   key in `sonar-project.properties` to the ones it shows, choose GitHub Actions analysis (Automatic Analysis off),
   and add the token as the `SONAR_TOKEN` secret. Until then the Sonar job skips its steps.
7. **Optional `SCORECARD_READ_TOKEN`**: a fine-grained PAT with read-only Administration lets Scorecard's
   Branch-Protection check read rulesets.
8. **OpenSSF Best Practices**: register the repository at <https://www.bestpractices.dev>.

## Scorecard checks that stay low for a solo maintainer

Code-Review and Contributors (one maintainer), Branch-Protection (no second approver), Fuzzing (none), Packaging
(HACS installs from the tag, no package registry).
