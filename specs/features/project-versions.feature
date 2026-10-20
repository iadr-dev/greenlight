@FEAT-103
Feature: A project from a newer greenlight is never touched
  Every command checks the schema version of the project first. A project that a newer greenlight wrote is refused
  with a message that says to upgrade, so older tooling cannot damage data it does not understand.

  @R-103.1
  Rule: Every command refuses a project that is newer than the installed greenlight

    @EX-103.1.1
    Scenario: Status refuses a newer project
      Given the input file newer project config contains:
        """
        version = 2
        """
      When alice runs status
      Then the command fails with usage error
      And the stderr output contains:
        """
        upgrade greenlight
        """

    @EX-103.1.2
    Scenario: Migrate refuses a newer project too
      Given the input file newer project config contains:
        """
        version = 2
        """
      When alice runs migrate
      Then the command fails with usage error
      And the stderr output contains:
        """
        upgrade greenlight
        """

  @R-103.2
  Rule: A project at the current version needs no migration

    @EX-103.2.1
    Scenario: Migrate has nothing to do
      Given the input file project config contains:
        """
        version = 1
        """
      When alice runs migrate
      Then the command succeeds
      And the stdout output contains:
        """
        nothing to do
        """
