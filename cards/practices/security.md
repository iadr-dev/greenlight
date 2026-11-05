---
id: security
kind: practice
apply_when: writing or reviewing code that signs people in, decides who may do what, handles money, secrets or personal data, or takes input from outside the process
output: code that checks access on the server for each record, validates input at the boundary, keeps secrets and personal data out of code, logs and errors, and cannot repeat a payment
phase: implement
pairs_with: [api-design, database-schema, language-typescript, language-python, language-go, language-kotlin]
---
## Intent

Most security defects in application code are a missing check, not a broken algorithm: an operation that trusts the
caller, an input used before it was validated, a secret in a log. Write the checks where the trust boundary is, the
same way every time, and use the project's and the platform's proven libraries instead of writing your own. The
Security section of `.bdd/standards.md` is the project's rule; this card is how to meet it.

## How to apply

1. **Access on the server, per record.** For every operation: who is asking (authenticated), and may they act on
   *this* record (ownership, tenant, role)? Look the record up with the caller's scope (`where owner_id = :caller`)
   rather than fetching by id and checking later. Deny by default; a check in the client or a hidden button is not a
   check. A scenario shows the caller who may not.
2. **Validate at the boundary.** Every request body, query, header, file, message and URL is parsed against a schema
   (the project's validation library) before it is used, and anything unknown is rejected, not ignored. Queries are
   parameterised; no SQL, shell command, file path, template or regular expression is built from input. Uploaded files
   are checked by content and size, stored outside the web root, and served with a safe type.
3. **Secrets.** No key, token or password in the code, the repository, the client bundle, a log or an error. Read them
   from the source the project uses (environment, a secrets manager) and fail at startup when one is missing, instead
   of falling back to a default. A secret that was exposed is rotated, not only deleted.
4. **Tokens and sessions.** Use the project's auth library. Fix the token algorithm and reject `none`; check expiry,
   issuer and audience. In a browser, keep session tokens in `HttpOnly`, `Secure`, `SameSite` cookies, and protect
   requests that change data against cross-site requests. Hash passwords with a slow, salted algorithm (Argon2id,
   bcrypt, scrypt) from a library.
5. **Output.** Escape for the place the data goes: HTML (the framework's escaping, never raw HTML from input), URLs,
   headers, logs. Outbound requests go only to an allowlist of hosts; a URL from input is never fetched as is.
6. **Errors and logs.** A caller sees a stable error code and a plain message, never a stack trace, a query or a file
   path. Never log passwords, tokens, full card numbers or personal data; log the identifier and the decision instead.
7. **Money.** Amounts in integer minor units or a decimal type, never floating point. An operation that charges,
   refunds or moves a balance takes an idempotency key and is safe to retry; webhooks are verified by signature,
   deduplicated by event id, and handled in any order.
8. **Abuse.** Rate-limit sign-in, password reset, anything that sends a message and anything that costs money, as the
   standards say. Lock out or slow down repeated failures without telling an attacker which part was wrong.
9. **Check it.** Run the project's security tools (a dependency audit, a SAST or secret scanner) through
   `[adapters.quality.NAME]`; read the diff for each point above; for every new operation name the scenario that shows
   a refused caller.

## Known pitfalls

- Checking that a caller is signed in but not that the record is theirs (the commonest real defect: change the id in
  the URL and read someone else's data).
- Validating in the client only, or validating and then using the raw input instead of the parsed value.
- A default secret in code "for development" that reaches production, or a missing secret that silently becomes an
  empty string.
- Logging the whole request or the whole user object, which carries tokens and personal data.
- `innerHTML`, `dangerouslySetInnerHTML`, `v-html`, string-built SQL or `eval` with data that came from outside.
- A retry, a double click or a replayed webhook that charges twice.
- Rolling your own crypto, token format or password hashing.
- Error messages that say whether an account exists ("wrong password" against "no such user").
