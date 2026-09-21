# Contributing a sanitized account fixture

Authenticated WebOPAC pages contain personal data. Never publish a raw page.

1. Save the HTML of the loans page locally.
2. Replace the reader's name, card number, email address, address, birth date,
   session tokens, cookies, barcodes, reservation numbers, and internal IDs.
3. Replace titles and authors with synthetic values while preserving the HTML
   structure and CSS classes.
4. Remove scripts, analytics identifiers, comments, and unrelated page content.
5. Confirm that searching the fixture for the real name, card number, and titles
   produces no matches.
6. Add a parser test that documents the expected fields.

Keep field names, form actions, tag names, CSS classes, and the shape of ASP.NET
hidden fields intact. Hidden-field values themselves must be replaced with
obvious placeholders such as `SANITIZED_VIEWSTATE`.

For private validation, open an issue first and agree on a secure transfer
method with a maintainer. Do not send library credentials.
