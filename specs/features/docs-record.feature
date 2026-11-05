@FEAT-108
Feature: The documentation a task was written from is on record
  A writer reads the current documentation of the libraries it calls before it writes code against them. The
  orchestrator records what it read for each task, with the version and a source anyone can open, so a reviewer and the
  auditor can check the code against it.

  @R-108.1
  Rule: A record names the task, the library, its version and a source that can be opened

    @EX-108.1.1
    Scenario: Recording the documentation read for a task
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts

          @R-007.1
          Rule: Orders of 1000 or more get 10% off

            @EX-007.1.1
            Scenario: A big order
              When alice runs export discounts
              Then the command succeeds
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file tasks contains:
        """
        ## T-007.1 Discounts

        Covers: EX-007.1.1
        """
      When alice runs docs with:
        | key | value                                          |
        | arg | FEAT-007                                       |
        | arg | --task                                         |
        | arg | T-007.1                                        |
        | arg | --library                                      |
        | arg | requests                                       |
        | arg | --version                                      |
        | arg | 2.32.3                                         |
        | arg | --source                                       |
        | arg | https://requests.readthedocs.io/en/latest/     |
      Then the command succeeds
      And the stdout output contains:
        """
        recorded: T-007.1 requests 2.32.3
        """
      And the output file docs record contains:
        """
        "library": "requests"
        """

    @EX-108.1.2
    Scenario: A source that cannot be opened is refused
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts

          @R-007.1
          Rule: Orders of 1000 or more get 10% off

            @EX-007.1.1
            Scenario: A big order
              When alice runs export discounts
              Then the command succeeds
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file tasks contains:
        """
        ## T-007.1 Discounts

        Covers: EX-007.1.1
        """
      When alice runs docs with:
        | key | value        |
        | arg | FEAT-007     |
        | arg | --task       |
        | arg | T-007.1      |
        | arg | --library    |
        | arg | requests     |
        | arg | --version    |
        | arg | 2.32.3       |
        | arg | --source     |
        | arg | from memory  |
      Then the command fails with usage error
      And the stderr output contains:
        """
        the source must be an https address or a file that exists
        """

    @EX-108.1.3
    Scenario: A version file is not documentation
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts

          @R-007.1
          Rule: Orders of 1000 or more get 10% off

            @EX-007.1.1
            Scenario: A big order
              When alice runs export discounts
              Then the command succeeds
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file tasks contains:
        """
        ## T-007.1 Discounts

        Covers: EX-007.1.1
        """
      And the input file package manifest contains:
        """
        {"dependencies": {"next": "16.4.5"}}
        """
      When alice runs docs with:
        | key | value        |
        | arg | FEAT-007     |
        | arg | --task       |
        | arg | T-007.1      |
        | arg | --library    |
        | arg | next         |
        | arg | --version    |
        | arg | 16.4.5       |
        | arg | --source     |
        | arg | package.json |
      Then the command fails with usage error
      And the stderr output contains:
        """
        a version file is not documentation
        """

  @R-108.2
  Rule: A task that calls no library says so, with a reason

    @EX-108.2.1
    Scenario: Recording that a task needs no documentation
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts

          @R-007.1
          Rule: Orders of 1000 or more get 10% off

            @EX-007.1.1
            Scenario: A big order
              When alice runs export discounts
              Then the command succeeds
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file tasks contains:
        """
        ## T-007.1 Discounts

        Covers: EX-007.1.1
        """
      When alice runs docs with:
        | key | value                                     |
        | arg | FEAT-007                                  |
        | arg | --task                                    |
        | arg | T-007.1                                   |
        | arg | --none                                    |
        | arg | arithmetic on the order total only        |
      Then the command succeeds
      And the output file docs record contains:
        """
        "kind": "none"
        """
