@FEAT-103
Feature: Setup suggests the adapter that fits the repository
  When a person sets greenlight up, it looks at the repository and says which test adapter fits and why. A Node or
  TypeScript service gets the adapter for Node code; a repository it cannot place gets no suggestion.

  @R-103.1
  Rule: A package manifest that names a Node framework or a command-line library suggests the Node adapter

    @EX-103.1.1
    Scenario: A Node web service
      Given the input file package manifest contains:
        """
        {"dependencies": {"express": "5.0.0"}}
        """
      When alice runs detect adapters
      Then the command succeeds
      And the stdout output contains:
        """
        ts-cucumber-js: package.json mentions express
        """

    @EX-103.1.2
    Scenario: A command-line tool
      Given the input file package manifest contains:
        """
        {"dependencies": {"commander": "14.0.0"}}
        """
      When alice runs detect adapters
      Then the command succeeds
      And the stdout output contains:
        """
        ts-cucumber-js: package.json mentions commander
        """

  @R-103.2
  Rule: A repository with nothing to recognise gets no suggestion

    @EX-103.2.1
    Scenario: An empty repository
      When alice runs detect adapters
      Then the command succeeds
      And the stdout output contains:
        """
        no adapter matched this repository
        """
