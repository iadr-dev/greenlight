Feature: Payloads

  Scenario: A table and then a doc string
    Given the following users exist:
      | name  | role  |
      | alice | admin |
      | bob   | user  |
    When alice posts the message:
      """json
      {
        "text": "hello",
        "nested": {"ok": true}
      }
      """
    Then the response contains:
      ```
      done
        indented line
      ```
