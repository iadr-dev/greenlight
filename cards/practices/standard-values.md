---
id: standard-values
kind: practice
apply_when: a feature stores, shows or asks for a phone number, a country, money, a time zone, an address, an email, a URL, a date or duration, a language, or a file
output: a Building blocks row per field of design.md that names the field's standard, the library or platform API that handles it, and its documentation
phase: system-map
pairs_with: [api-design, database-schema, accessibility]
---
## Intent

Some values have a standard that the whole world already agreed on, and a library that knows its rules. A phone number
kept as free text cannot be dialled from abroad, compared or validated; a price kept as a float loses cents; a time zone
kept as an offset is wrong half the year. Choose the standard and the library in the design, before the code, so the
API, the database and the screen agree on one form.

## How to apply

1. For every field of the Design trace in `design.md` that has an API field, write a row of the Building blocks table:
   the field, its kind, the standard, the library or platform API, the package (`npm:NAME`, `pypi:NAME`, ... or `-` for
   a platform API) and the documentation you read. `bdd design FEAT-n` refuses a field of a kind below without its
   standard.
2. Use the table to pick them. The library is the one for the project's language; when the project has none yet, the
   person adds it with the one line `bdd gate FEAT-n tasks` prints.

   | Kind | Standard | Library or platform API | Source |
   |---|---|---|---|
   | phone | E.164 (`+` and at most 15 digits), stored as E.164 | libphonenumber: `libphonenumber-js` (JS), `phonenumbers` (Python), `com.googlecode.libphonenumber` (Java, Kotlin), `github.com/nyaruka/phonenumbers` (Go), `libphonenumber-csharp` (.NET), `PhoneNumberKit` (Swift), `phone_numbers_parser` (Dart); a country-code picker beside the number | https://www.itu.int/rec/T-REC-E.164, https://github.com/google/libphonenumber |
   | country | ISO 3166-1 alpha-2 code (`JP`, `DE`) | names from the platform in the person's language: `Intl.DisplayNames` with `type: "region"` (JS), `Locale.localizedString(forRegionCode:)` (Swift), `Locale("", code).displayCountry` (Kotlin), Babel's `Locale.territories` (Python); never a hand-written list of names | https://www.iso.org/iso-3166-country-codes.html, https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DisplayNames |
   | money | ISO 4217 currency code, the amount in integer minor units (cents; 0 decimals for JPY, 3 for KWD) | `Intl.NumberFormat` with `style: "currency"` (JS), Babel's `format_currency` (Python), `NumberFormatter` (Swift), `NumberFormat.getCurrencyInstance` (Kotlin); a decimal or integer column, never a float | https://www.iso.org/iso-4217-currency-codes.html, https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat |
   | time zone | IANA time zone name (`Asia/Tokyo`), never an offset | `Intl.supportedValuesOf("timeZone")` for the list (JS), `zoneinfo` (Python), `java.time.ZoneId`, `TimeZone` (Swift) | https://www.iana.org/time-zones |
   | date, time, duration | ISO 8601 / RFC 3339 on the wire; an instant stored in UTC with the person's IANA zone beside it when local time matters; a birthday is a date without a zone; a duration in ISO 8601 (`PT30M`) or whole seconds | the platform's date API (`Temporal` or `Intl.DateTimeFormat` in JS, `datetime` in Python, `java.time`) | https://www.rfc-editor.org/rfc/rfc3339 |
   | address | the country's own format: the fields, their order and which are required differ per country | Google's address metadata (`libaddressinput`), or a place-search API (Google Places Autocomplete, Mapbox Search) recorded as an outside call | https://github.com/google/libaddressinput |
   | email | the `type=email` rule of the HTML standard to catch typos; proof of the address by sending to it | the platform's input type; at most 254 characters; compare without regard to the case of the domain | https://html.spec.whatwg.org/multipage/input.html#email-state-(type=email) |
   | URL | the WHATWG URL standard; only `https` (and the schemes the feature names) accepted | `new URL()` (JS), `urllib.parse` (Python), `java.net.URI` | https://url.spec.whatwg.org/ |
   | language, locale | BCP 47 language tag (`pt-BR`) | `Intl.Locale` (JS), Babel (Python), `Locale` (Swift, Kotlin) | https://www.rfc-editor.org/info/bcp47 |
   | file, image | IANA media type, checked from the file's content, not its name; a size limit | the platform's file API; an image library that strips location data and resizes | https://www.iana.org/assignments/media-types/media-types.xhtml |

3. Name the same form in the API contract (the field's type and pattern), in the database (the column type and its
   length) and in the screen (the input, its picker and its format), so the three cannot drift apart.

## Known pitfalls

- A phone number as free text of some length: it cannot be dialled from abroad or compared. Store E.164 and show it in
  the national format the library gives.
- A country-code picker built from a list of names typed by hand: they are in one language and age. Take the names from
  the platform in the person's language.
- Money as a float (`0.1 + 0.2`), or a currency without its code. Keep integer minor units and the ISO 4217 code together.
- A time zone saved as `+09:00`: the offset changes with daylight saving time. Save the IANA name.
- An address form with a US-shaped "state" and "ZIP": it fails for most countries. Use the country's format or a place
  search.
- An email checked with a long regular expression: it refuses real addresses. Check the shape loosely and send a link.
- A file type taken from its name, or an image served with the location in its EXIF data.
- This card ages. Each row names its source; check them when a standard or library changes.
