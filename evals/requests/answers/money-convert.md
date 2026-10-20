# Scripted answers: money-convert

- Rounding mode? Half up, away from zero for negative amounts (-0.5 rounds to -1).
- Is the rate validated against a table of rates? No, the caller passes it.
- Which currencies? The ones the library already knows: USD, EUR, JPY.
- What does converting to the same currency do with a rate other than 1? The rate is ignored and the amount is returned unchanged.
- What is refused? A rate of zero or less, and an unknown target currency, with a MoneyError.
