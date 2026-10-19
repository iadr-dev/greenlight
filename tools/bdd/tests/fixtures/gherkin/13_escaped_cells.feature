Feature: Escapes

  Scenario: Escaped characters in cells
    Given the table:
      | text        | note             |
      | a \| b      | pipe             |
      | c \\ d      | backslash        |
      | line1\nline2 | newline          |
      |             | empty first cell |
