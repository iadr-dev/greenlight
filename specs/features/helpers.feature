@FEAT-107
Feature: The person decides once whether to be offered the helper plugins
  greenlight works without any helper plugin. Setup offers them once; a person who says "do not ask again" is not asked
  again in that project, and nothing is installed by anyone but the person.

  @R-107.1
  Rule: Declining is remembered in the project

    @EX-107.1.1
    Scenario: Do not ask again
      Given the input file project config contains:
        """
        # greenlight project settings
        """
      When alice runs helpers with:
        | key | value     |
        | arg | --decline |
      Then the command succeeds
      And the stdout output contains:
        """
        will not offer the helper plugins again
        """
      And the output file helpers record contains:
        """
        "decision": "declined"
        """

  @R-107.2
  Rule: Installing needs the person's confirmation

    @EX-107.2.1
    Scenario: Install without confirming
      When alice runs helpers with:
        | key | value        |
        | arg | install      |
        | arg | not-a-helper |
      Then the command fails with usage error
      And the stderr output contains:
        """
        not a helper: not-a-helper
        """
