@FEAT-106
Feature: Each task goes to the roles its scenarios need
  The orchestrator does not ask the person who should write or review a task. greenlight reads which steps the task's
  scenarios use and the words of the feature's rules, and names the writer, the reviewers and the cards to read, the
  same way every time.

  @R-106.1
  Rule: A task whose scenarios open or check a screen goes to the UI engineer and is reviewed for the UI and the code

    @EX-106.1.1
    Scenario: A task with a screen
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
          Rule: The discount shows on the order

            @EX-007.1.1
            Scenario: The banner shows the discount
              When alice opens the orders page
              Then alice sees the discount banner showing:
                | text    |
                | 10% off |
        """
      And the input file tasks contains:
        """
        ## T-007.1 Discount banner

        Covers: EX-007.1.1
        """
      When alice runs route with:
        | key | value    |
        | arg | FEAT-007 |
      Then the command succeeds
      And the stdout output contains:
        """
        writer: ui-engineer
          reviewers: code-reviewer, ui-reviewer
        """

  @R-106.2
  Rule: Any other task goes to the implementer and the code reviewer

    @EX-106.2.1
    Scenario: A task with a command line
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
          Rule: The export lists the discounts

            @EX-007.1.1
            Scenario: Exporting the discounts
              When alice runs export discounts
              Then the command succeeds
        """
      And the input file tasks contains:
        """
        ## T-007.1 Export

        Covers: EX-007.1.1
        """
      When alice runs route with:
        | key | value    |
        | arg | FEAT-007 |
      Then the command succeeds
      And the stdout output contains:
        """
        writer: implementer
          reviewers: code-reviewer
        """

  @R-106.3
  Rule: A task about signing in, money or personal data also goes to the security reviewer

    @EX-106.3.1
    Scenario: A task with a signed-in actor
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
          Rule: Only an admin exports the discounts

            @EX-007.1.1
            Scenario: An admin exports the discounts
              Given alice is signed in as admin
              When alice runs export discounts
              Then the command succeeds
        """
      And the input file tasks contains:
        """
        ## T-007.1 Export for admins

        Covers: EX-007.1.1
        """
      When alice runs route with:
        | key | value    |
        | arg | FEAT-007 |
      Then the command succeeds
      And the stdout output contains:
        """
        reviewers: code-reviewer, security-reviewer
        """
