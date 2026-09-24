# Covers on a Home Assistant dashboard

Each current loan with a supported HTTPS cover gets an `image.*` entity named
`<book title> Cover`, attached to the same library-account device as the sensors.
After updating through HACS, restart Home Assistant and open the WinBIAP device
under **Settings → Devices & services → WinBIAP Library** to find these entities.

The images are served through Home Assistant's image proxy. The browser does not
need a library login, and the integration never sends account cookies to cover
providers. Images are fetched on demand, cached in memory and bounded to 2 MiB.
Returned loans become unavailable. New loans get images at the next account
refresh. Media without a usable cover keep their loan sensor but have no cover
entity until a cover becomes available.

## Individual book card

Add a built-in **Picture entity** card and select the book's image entity. In YAML,
replace the example ID below with an actual entity from your device:

```yaml
type: picture-entity
entity: image.example_book_cover
show_name: true
show_state: false
fit_mode: contain
tap_action:
  action: more-info
```

The image's attributes include title, author, due date, days remaining and renewal
eligibility, so custom cards can place the cover beside the book information.
Do not copy image access tokens into a static card; let Home Assistant use the
image entity and manage its rotating proxy token.

## Automatic list with built-in Markdown

This card discovers all WinBIAP cover entities and shows a compact list without
additional HACS frontend cards. It updates when entity states change. Returned
or currently unavailable books are omitted. With several library accounts,
replace `integration_entities('winbiap')` with the desired config-entry ID.

```yaml
type: markdown
title: Bibliothek – Ausleihen
content: >-
  {% set covers = integration_entities('winbiap') | select('match', '^image[.]') | list %}
  {% for entity in covers | sort %}
  {% if has_value(entity) %}
  <img src="{{ state_attr(entity, 'entity_picture') }}" width="80">

  **{{ state_attr(entity, 'title') }}**

  {{ state_attr(entity, 'author') or '' }}

  Rückgabe: {{ state_attr(entity, 'due_date') }} · Noch {{ state_attr(entity, 'days_remaining') }} Tage

  ---
  {% endif %}
  {% endfor %}
```

Keep the dashboard restricted to the intended users: loan titles and due dates
are personal account data even though the cover pictures themselves are public.

## Complete dynamic view

`examples/buecherei.json` contains the responsive loan view, reservations, current fees and wishlist overview.
It discovers WinBIAP entities dynamically and uses the installed card-mod resource
for styling. Import it as the Bücherei view in a storage dashboard.

## Personal return planning

The first card now displays renewal status per book and the last in-person return
window above the counters. It uses the new return-deadline timestamp entity and
opening-hours metadata, not a hard-coded weekly schedule. Missing/stale hours keep
the library due date visible without inventing a visit deadline. Configure dated
closures or special hours through the integration options. Source support currently
covers Königsbrunn; the weekly schedule alone cannot guarantee unannounced closures.
