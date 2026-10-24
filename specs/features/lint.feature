@FEAT-101
Feature: Lint checks feature files against the step vocabulary
  A developer runs lint on the feature files. It reports every step the vocabulary does not know, and every
  scenario that cannot be traced to a rule and an example.

  @R-101.1
  Rule: A feature whose steps all come from the vocabulary and whose scenarios are traced passes

    @EX-101.1.1
    Scenario: A well-formed feature passes
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
          Rule: Big orders get a discount

            @EX-007.1.1
            Scenario: Just below the threshold
              Given alice is signed in as member
              Then the request succeeds
        """
      When alice runs lint with:
        | key | value    |
        | arg | features |
      Then the command succeeds
      And the stdout output contains:
        """
        0 error(s)
        """

  @R-101.4
  Rule: A swipe, a scroll and going back are steps of the vocabulary

    @EX-101.4.1
    Scenario: A screen scenario with the gestures passes
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
        Feature: Order list

          @R-007.1
          Rule: A person can browse the orders

            @EX-007.1.1
            Scenario: Scrolling, swiping and going back
              When alice scrolls order list with:
                | direction |
                | down      |
              And alice swipes first order card with:
                | direction |
                | left      |
              And alice goes back
              Then alice sees order list showing:
                | item |
                | 7    |
        """
      When alice runs lint with:
        | key | value    |
        | arg | features |
      Then the command succeeds
      And the stdout output contains:
        """
        0 error(s)
        """

  @R-101.2
  Rule: A step that no vocabulary entry matches is reported with its code

    @EX-101.2.1
    Scenario: An unknown step is refused
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
          Rule: Big orders get a discount

            @EX-007.1.1
            Scenario: Just below the threshold
              Given the moon is full
              Then the request succeeds
        """
      When alice runs lint with:
        | key | value    |
        | arg | features |
      Then the command fails with violations found
      And the stdout output contains:
        """
        L002
        """

  @R-101.3
  Rule: A scenario without trace tags is reported, so every example can be traced to a rule

    @EX-101.3.1
    Scenario: Missing trace tags are refused
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file feature file contains:
        """
        Feature: Discounts

          Scenario: Just below the threshold
            Given alice is signed in as member
            Then the request succeeds
        """
      When alice runs lint with:
        | key | value    |
        | arg | features |
      Then the command fails with violations found
      And the stdout output contains:
        """
        L005
        """
