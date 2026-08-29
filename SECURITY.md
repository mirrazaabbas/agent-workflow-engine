# Security Policy

## Supported branch

The `main` branch is the actively maintained version of this portfolio project.

## Reporting a vulnerability

Please do not publish secrets, credentials, private data, or actionable exploit details in a public issue. If GitHub private vulnerability reporting is available for this repository, use that channel. Otherwise, open a minimal issue stating that you found a security concern and avoid including sensitive reproduction details until a private channel is established.

## Security principles

- Never commit API keys, tokens, passwords, or private datasets.
- Treat workflow input and future tool/model output as untrusted data.
- Validate inputs before executing protected or high-impact steps.
- Use the built-in approval-gate pattern for actions that should require human authorization.
- Keep external tool permissions scoped to the minimum required access.
- Avoid logging credentials or sensitive workflow state.
