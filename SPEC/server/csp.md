## SERVER-CSP-001 — The Content-Security-Policy contains only valid sources

Implement: the `Content-Security-Policy` header set by the security middleware
in `app/main.py`, sent with every response of the application created by
`app.main.create_app`.
Out of scope: allowing the restart poll towards an IPv6 address — CSP
host-sources cannot express IPv6 literals, so that case keeps the manual
link shown in the restart panel.

Test: unit · `tests/test_api.py` · `test_server_csp_001_policy_has_only_valid_sources`
- Given: the application with a default `Config()`
- When: `GET /` is requested
- Then: `connect-src` is exactly `'self' http://127.0.0.1:*`, and every source
  of every directive is a CSP keyword, a scheme such as `data:`, or a
  host-source without brackets (so no `http://[::1]:*`)
