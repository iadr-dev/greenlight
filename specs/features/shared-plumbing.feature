@FEAT-111
Feature: Shared test plumbing is locked once for the project
  Every feature's tests run on the same plumbing: the runner settings, the package manifests and the drivers the
  adapter ships. It is locked once for the project, not by every feature. A feature's bind lock covers its own step
  and driver files, so binding the next feature never reopens the one before it, and a change to the plumbing is its
  own change, after which every feature reruns its scenarios once.

  @R-111.1
  Rule: A file another feature binds later is that feature's file, not a violation of the feature bound before it

    @EX-111.1.1
    Scenario: Binding a second feature with a new step file leaves the first feature's lock intact
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file rules contains:
        """
        R-007.1 Orders of 1000 or more get 10% off.
        """
      And the input file second rules contains:
        """
        R-008.1 A refund returns the amount paid.
        """
      And the input file step file contains:
        """
        # discount steps
        """
      And the input file second step file contains:
        """
        # refund steps
        """
      When alice runs lock with:
        | key | value         |
        | arg | FEAT-007      |
        | arg | --scope       |
        | arg | bind          |
        | arg | steps/steps.py |
      And alice runs lock with:
        | key | value    |
        | arg | FEAT-008 |
        | arg | --scope  |
        | arg | bind     |
        | arg | --bound  |
      And alice runs lock with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --check  |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007: locks intact (bind: 1 file(s)); plumbing: 0 file(s)
        """

  @R-111.2
  Rule: A change to the shared plumbing fails every feature's check until it is locked again, with a reason

    @EX-111.2.1
    Scenario: A changed plumbing file that was not locked again fails the check
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        support = ["steps/conftest.py"]
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts
        """
      And the input file step file contains:
        """
        # discount steps
        """
      And the input file support file contains:
        """
        # shared fixtures
        """
      And the input file plumbing lock record contains:
        """
        {"schema": 1, "locked_at": "2026-01-01T00:00:00+00:00", "unlocked": null, "history": [],
         "files": {"steps/conftest.py": "0000000000000000000000000000000000000000000000000000000000000000"}}
        """
      And the input file lock record contains:
        """
        {"schema": 1, "feature": "FEAT-007", "history": [],
         "scopes": {"bind": {"locked_at": "2026-01-01T00:00:00+00:00", "plumbing": "earlier",
                             "files": {"steps/steps.py": "22148216b05d7c9477a312f7857cdabfb2d689c6e951806e6d43d8f45b5b5c63"}}}}
        """
      When alice runs lock with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --check  |
      Then the command fails with violations found
      And the stdout output contains:
        """
        [plumbing] steps/conftest.py is shared test plumbing and changed since the project locked it
        """

    @EX-111.2.2
    Scenario: Locking the plumbing again names every feature to rerun and reopens none
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        support = ["steps/conftest.py"]
        """
      And the input file step file contains:
        """
        # discount steps
        """
      And the input file second step file contains:
        """
        # refund steps
        """
      And the input file support file contains:
        """
        # shared fixtures
        """
      And the input file plumbing lock record contains:
        """
        {"schema": 1, "locked_at": "2026-01-01T00:00:00+00:00", "unlocked": null, "history": [],
         "files": {"steps/conftest.py": "0000000000000000000000000000000000000000000000000000000000000000"}}
        """
      And the input file lock record contains:
        """
        {"schema": 1, "feature": "FEAT-007", "history": [],
         "scopes": {"bind": {"locked_at": "2026-01-01T00:00:00+00:00", "plumbing": "earlier",
                             "files": {"steps/steps.py": "22148216b05d7c9477a312f7857cdabfb2d689c6e951806e6d43d8f45b5b5c63"}}}}
        """
      And the input file second lock record contains:
        """
        {"schema": 1, "feature": "FEAT-008", "history": [],
         "scopes": {"bind": {"locked_at": "2026-01-02T00:00:00+00:00", "plumbing": "earlier",
                             "files": {"steps/refunds.py": "8ee80104af176707c75312d700dd31d7305235fdd0c8818db144ffafe177579b"}}}}
        """
      When alice runs lock with:
        | key | value                            |
        | arg | --plumbing                       |
        | arg | --reason                         |
        | arg | the shared fixtures gained a clock |
      Then the command succeeds
      And the stdout output contains:
        """
        every bound feature reruns its scenarios once; none is reopened:
          FEAT-007
          FEAT-008
        """

    @EX-111.2.3
    Scenario: After the plumbing is locked again, a feature's check passes without reopening it
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        support = ["steps/conftest.py"]
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts
        """
      And the input file step file contains:
        """
        # discount steps
        """
      And the input file support file contains:
        """
        # shared fixtures
        """
      And the input file plumbing lock record contains:
        """
        {"schema": 1, "locked_at": "2026-01-01T00:00:00+00:00", "unlocked": null, "history": [],
         "files": {"steps/conftest.py": "0000000000000000000000000000000000000000000000000000000000000000"}}
        """
      And the input file lock record contains:
        """
        {"schema": 1, "feature": "FEAT-007", "history": [],
         "scopes": {"bind": {"locked_at": "2026-01-01T00:00:00+00:00", "plumbing": "earlier",
                             "files": {"steps/steps.py": "22148216b05d7c9477a312f7857cdabfb2d689c6e951806e6d43d8f45b5b5c63"}}}}
        """
      When alice runs lock with:
        | key | value                            |
        | arg | --plumbing                       |
        | arg | --reason                         |
        | arg | the shared fixtures gained a clock |
      And alice runs lock with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --check  |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007: locks intact
        """

    @EX-111.2.4
    Scenario: Locking the plumbing again without a reason is refused
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        support = ["steps/conftest.py"]
        """
      And the input file support file contains:
        """
        # shared fixtures
        """
      When alice runs lock with:
        | key | value      |
        | arg | --plumbing |
      Then the command fails with usage error
      And the stderr output contains:
        """
        --reason
        """

  @R-111.3
  Rule: A lock made before the plumbing lock existed is converted by migrate, and its check stays clean

    @EX-111.3.1
    Scenario: Migrating an old lock moves the shared file into the plumbing lock
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        support = ["steps/conftest.py"]
        """
      And the input file feature file contains:
        """
        @FEAT-007
        Feature: Discounts
        """
      And the input file step file contains:
        """
        # discount steps
        """
      And the input file support file contains:
        """
        # shared fixtures
        """
      And the input file lock record contains:
        """
        {"schema": 1, "feature": "FEAT-007", "history": [],
         "scopes": {"bind": {"locked_at": "2026-01-01T00:00:00+00:00",
                             "files": {"steps/steps.py": "22148216b05d7c9477a312f7857cdabfb2d689c6e951806e6d43d8f45b5b5c63",
                                       "steps/conftest.py": "dc69858f555e09597acb0b50db77f2f6a6ad7d72a8b3d510debb95ca43daf624"}}}}
        """
      When alice runs migrate
      And alice runs lock with:
        | key | value    |
        | arg | FEAT-007 |
        | arg | --check  |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-007: locks intact (bind: 1 file(s)); plumbing: 1 file(s)
        """
