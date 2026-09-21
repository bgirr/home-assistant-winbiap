# Diagnosing setup and login

The setup flow validates the selected WebOPAC account before saving it. It
shows a form error for a missing login form, a returned login page, a page
layout it cannot parse, a connection failure, or a 30-second timeout.

To collect a focused trace while adding a new account, run the
`logger.set_level` action in **Developer tools → Actions**:

```yaml
action: logger.set_level
data:
  custom_components.winbiap: debug
```

Retry setup once, then inspect **Settings → System → Logs → Home Assistant
Core**. The relevant loggers are `custom_components.winbiap.api` and
`custom_components.winbiap.config_flow`. To restore normal logging, run:

```yaml
action: logger.set_level
data:
  custom_components.winbiap: warning
```

The integration logs the request stage, HTTP status, and a categorical result.
It does not log passwords, library-card numbers, cookies, HTML or complete
WebOPAC URLs. When sharing logs, check them once more for data from other
integrations and omit any account identifiers. Report the selected library
name, the error displayed in the form and the WinBIAP log lines. An
authenticated HTML page is still needed to support a new account layout;
follow [fixtures.md](fixtures.md) to sanitize it before sharing.
