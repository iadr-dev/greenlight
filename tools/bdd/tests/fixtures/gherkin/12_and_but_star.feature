Feature: Keyword inheritance

  Scenario: And, But and star inherit the previous kind
    Given a user
    And an admin
    * a guest
    When they log in
    And they log out
    Then they are gone
    But the audit log remains
    * and so does the backup
