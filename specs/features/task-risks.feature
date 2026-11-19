@FEAT-118
Feature: Implement against the design, with the known risks of each task
  Each task of a feature knows which sections of its technical design it builds and which known risks its code must
  handle: concurrent writes, retries, rate limits, storage errors, authorisation, personal data, time zones and large
  lists. greenlight names them from the task's steps, the feature's rules and the design, the code reviewer answers each
  one, the project's own checks run after every task, independent tasks may be built at the same time, and the UI
  reviewer compares each built screen with its design or says why it could not.

  Background:
    Given the input file project config contains:
      """
      [[adapters]]
      name = "x"
      features = "features"
      steps = "steps"

      [adapters.quality.architecture]
      command = '{python} -c "pass"'

      [design]
      inventory = "design/inventory.md"
      """
    And the input file design inventory contains:
      """
      # Screen inventory

      | ID | Screen | States | Feature | File | Fields |
      |---|---|---|---|---|---|
      | O-SI-01 | Sign in | idle, signing in, error | FEAT-001 | screens/home.html | Google button |
      """
    And the input file sign-in feature file contains:
      """
      @FEAT-001
      Feature: Sign in

        @R-001.1
        Rule: A person signs in with their Google account

          @EX-001.1.1
          Scenario: Signing in with Google
            When alice calls create session with:
              | provider |
              | google   |
            Then the request succeeds

        @R-001.2
        Rule: The page offers the Google button

          @EX-001.2.1
          Scenario: The button is on the page
            When alice opens the welcome page
            Then alice sees the Google button showing:
              | text                |
              | Continue with Google |
      """
    And the input file sign-in rules contains:
      """
      R-001.1 A person signs in with their Google account.
      R-001.2 The page offers the Google button.
      """
    And the input file sign-in state contains:
      """
      {"schema": 1, "feature": "FEAT-001", "kind": "feature", "title": "Sign in", "created_at": "2026-11-19T10:00:00+00:00",
       "phase": "implement", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
       "red": null, "hooks_seen": false, "changes": [], "approvals": [], "technical_design": true, "against_design": true}
      """
    And the input file sign-in design contains:
      """
      # Design: FEAT-001 Sign in

      ## Design trace
      | Screen | Element | Rule | API field | Component |
      |---|---|---|---|---|
      | - | session | R-001.1 | session.user | - |
      | O-SI-01 Sign in | Google button | R-001.2 | - | GoogleButton |

      ## External services
      | Service | Call | Quota | Cost | On failure |
      |---|---|---|---|---|
      | google | sign in with OAuth 2.0 | 10000 a day | free | "Could not sign in, try again" |

      ## Architecture
      | Piece | Layer | Path |
      |---|---|---|
      | sign-in service | service | src/auth/signin.ts |

      ## Security and privacy
      | Kind | Subject | Decision | Enforced in |
      |---|---|---|---|
      | rate limit | POST /sessions | 10 a minute per address | the API |
      | authorisation | POST /sessions | anyone; the session is the person's own | the session service |
      """
    And the input file sign-in tasks contains:
      """
      ## T-001.1 Sign in with Google

      Covers: EX-001.1.1
      Areas: src/auth/
      Depends on: none
      Design: Design trace, External services, Architecture, Security and privacy
      Risks: concurrent writes, rate limits, authorisation

      ## T-001.2 The sign-in page

      Covers: EX-001.2.1
      Areas: src/pages/signin/
      Depends on: none
      Design: Design trace, State and offline; O-SI-01
      Risks: none
      """

  @R-118.1
  Rule: Each task names the design sections it builds and the known risks its code must handle

    @EX-118.1.1
    Scenario: A sign-in task names its risks and its design sections
      When alice runs route with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command succeeds
      And the stdout output contains:
        """
        risks: concurrent writes, rate limits, authorisation
        """
      And the stdout output contains:
        """
        design: Design trace, External services, Architecture, Security and privacy
        """
      And the stdout output contains:
        """
        services: google (sign in with OAuth 2.0)
        """

    @EX-118.1.2
    Scenario: A risk the orchestrator adds to a task is kept
      Given the input file sign-in tasks contains:
        """
        ## T-001.1 Sign in with Google

        Covers: EX-001.1.1, EX-001.2.1
        Design: Architecture
        Risks: time zones
        """
      When alice runs route with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command succeeds
      And the stdout output contains:
        """
        risks: concurrent writes, rate limits, authorisation, time zones
        """

    @EX-118.1.3
    Scenario: A risk greenlight does not know is reported once
      Given the input file sign-in tasks contains:
        """
        ## T-001.1 Sign in with Google

        Covers: EX-001.1.1
        Design: Architecture
        Risks: flakiness

        ## T-001.2 The sign-in page

        Covers: EX-001.2.1
        Design: Architecture
        Risks: flakiness, rate limits
        """
      When alice runs trace with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        T010 tasks.md names the risk "flakiness" (T-001.1, T-001.2), which is not one greenlight knows
        """

    @EX-118.1.4
    Scenario: A task list written before the risks still routes, and says once what it lacks
      Given the input file sign-in tasks contains:
        """
        ## T-001.1 Sign in with Google

        Covers: EX-001.1.1

        ## T-001.2 The sign-in page

        Covers: EX-001.2.1
        """
      When alice runs route with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command succeeds
      And the stdout output contains:
        """
        risks: concurrent writes, rate limits, authorisation
        """
      And the stdout output contains:
        """
        tasks.md has no Design: or Risks: line for T-001.1, T-001.2; the ones above are derived
        """

  @R-118.2
  Rule: The code reviewer answers every risk of its task

    @EX-118.2.1
    Scenario: A code review without a line for a risk of its task is refused
      Given the input file sign-in code review contains:
        """
        # code-reviewer: T-001.1 Sign in with Google

        Verdict: PASS

        ## Risks
        - Risk concurrent writes: handled in src/auth/signin.ts:14
        - Risk authorisation: handled in src/auth/signin.ts:30
        """
      When alice runs gate with:
        | key | value     |
        | arg | FEAT-001  |
        | arg | implement |
        | arg | --result  |
        | arg | pass      |
      Then the command fails with refused
      And the stderr output contains:
        """
        reviews/T-001.1-code-reviewer.md has no line for the risk "rate limits"
        """

    @EX-118.2.2
    Scenario: A risk the code reviewer marks missing is refused
      Given the input file sign-in code review contains:
        """
        # code-reviewer: T-001.1 Sign in with Google

        Verdict: PASS

        ## Risks
        - Risk concurrent writes: handled in src/auth/signin.ts:14
        - Risk rate limits: missing
        - Risk authorisation: handled in src/auth/signin.ts:30
        """
      When alice runs gate with:
        | key | value     |
        | arg | FEAT-001  |
        | arg | implement |
        | arg | --result  |
        | arg | pass      |
      Then the command fails with refused
      And the stderr output contains:
        """
        reviews/T-001.1-code-reviewer.md says the risk "rate limits" is missing
        """

  @R-118.3
  Rule: Tasks that share no files and wait for no other task may be built at the same time

    @EX-118.3.1
    Scenario: Independent tasks share a group and a task on the same files waits
      Given the input file sign-in tasks contains:
        """
        ## T-001.1 Sign in with Google

        Covers: EX-001.1.1
        Areas: src/auth/

        ## T-001.2 The sign-in page

        Covers: EX-001.2.1
        Areas: src/pages/signin/

        ## T-001.3 Remember the session

        Covers:
        Areas: src/auth/session.ts
        """
      When alice runs route with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command succeeds
      And the stdout output contains:
        """
        runs in: group 1, with T-001.2
        """
      And the stdout output contains:
        """
        runs in: group 2, after T-001.1
        """

  @R-118.4
  Rule: The project's checks, the architecture checker among them, run after every task

    @EX-118.4.1
    Scenario: The checks run for a task are recorded for that task
      When alice runs start a repository
      And alice runs check with:
        | key | value    |
        | arg | FEAT-001 |
        | arg | --task   |
        | arg | T-001.1  |
      Then the command succeeds
      And the stdout output contains:
        """
        recorded for T-001.1
        """

    @EX-118.4.2
    Scenario: The implement gate refuses a task whose checks were not run after it
      Given the input file sign-in quality result contains:
        """
        {"schema": 1, "feature": "FEAT-001", "at": "2026-11-19T10:00:00+00:00", "passed": true,
         "checks": [{"name": "architecture", "passed": true}],
         "tasks": {"T-001.1": {"at": "2026-11-19T10:00:00+00:00", "passed": true, "failed": []}}}
        """
      When alice runs start a repository
      And alice runs gate with:
        | key | value     |
        | arg | FEAT-001  |
        | arg | implement |
        | arg | --result  |
        | arg | pass      |
      Then the command fails with refused
      And the stderr output contains:
        """
        T-001.2 has no passing run of the quality checks of its own: run `bdd check FEAT-001 --task T-001.2` after the task
        """

  @R-118.5
  Rule: The UI reviewer compares each built screen with its design, or says why it could not

    @EX-118.5.1
    Scenario: A UI review that neither compares the screen nor says why is refused
      Given the input file sign-in ui review contains:
        """
        # ui-reviewer: T-001.2 The sign-in page

        Verdict: PASS

        ## Must fix
        ## Not checked
        - nothing
        """
      When alice runs gate with:
        | key | value     |
        | arg | FEAT-001  |
        | arg | implement |
        | arg | --result  |
        | arg | pass      |
      Then the command fails with refused
      And the stderr output contains:
        """
        reviews/T-001.2-ui-reviewer.md neither compares O-SI-01 with its design at 375 and 1280 px nor says under Not checked why it could not
        """
