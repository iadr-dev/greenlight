@FEAT-117
Feature: A checked technical design before code
  Before a feature's code is written, its technical design says how every screen element of the approved design is
  built: the rule it serves, the API field it reads and the component that shows it; the standard and library of every
  field; the evidence for every outside call; where each piece lives; the data, security, error, state, accessibility,
  observability, delivery and test decisions. greenlight checks the design and refuses the gaps by name, and the code,
  security and UI reviewers review it before the tasks are written.

  Background:
    Given the input file project config contains:
      """
      [[adapters]]
      name = "x"
      features = "features"
      steps = "steps"

      [design]
      inventory = "design/inventory.md"
      """
    And the input file design inventory contains:
      """
      # Screen inventory

      | ID | Screen | States | Feature | File | Fields |
      |---|---|---|---|---|---|
      | O-ST-01 | Company profile | loading, saved, error | FEAT-001 | screens/home.html | name, contact phone |
      """
    And the input file company state contains:
      """
      {"schema": 1, "feature": "FEAT-001", "kind": "feature", "title": "Company profile", "created_at": "2026-11-19T10:00:00+00:00",
       "phase": "system-map", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
       "red": null, "hooks_seen": false, "changes": [], "approvals": [], "technical_design": true}
      """
    And the input file company rules contains:
      """
      R-001.1 A company has a name.
      R-001.2 A company has a contact phone that can be dialled from abroad.
      """
    And the input file example source contains:
      """
      export const form = {};
      """
    And the input file technical design contains:
      """
      # Design: FEAT-001 Company profile

      ```mermaid
      flowchart LR
        ui[Profile screen] --> api[PATCH /company] --> db[(companies)]
      ```

      ## Design trace
      | Screen | Element | Rule | API field | Component |
      |---|---|---|---|---|
      | O-ST-01 Company profile | name | R-001.1 | company.name | TextField |
      | O-ST-01 Company profile | contact phone | R-001.2 | company.phone | PhoneInput |

      ## Building blocks
      | Field | Kind | Standard | Library | Package | Source |
      |---|---|---|---|---|---|
      | name | text | plain text, 1 to 120 characters | none | - | https://developer.mozilla.org/en-US/docs/Web/HTML/Element/input |
      | contact phone | phone | E.164 | libphonenumber-js | npm:libphonenumber-js | https://gitlab.com/catamphetamine/libphonenumber-js |

      ## External services
      | Service | Call | Quota | Cost | On failure |
      |---|---|---|---|---|
      | n/a | the profile calls no outside service | | | |

      ## Architecture
      | Piece | Layer | Path |
      |---|---|---|
      | company profile service | service | src/company/service.ts |

      ## Patterns
      | Pattern | Example file | Use for |
      |---|---|---|
      | form with server validation | src/orders/form.ts | the profile form |

      ## API contract
      | Endpoint | Request | Response | Version | Older clients |
      |---|---|---|---|---|
      | PATCH /company | name, phone in E.164 | 200 with the company | v1 | unchanged: they never sent a phone |

      ## Data and performance
      | Kind | Name | Detail | Index | Budget | Rollback |
      |---|---|---|---|---|---|
      | migration | add companies.phone | varchar(16), E.164 | - | - | drop the column |
      | query | company by owner | where owner_id = ? | companies_owner_id_idx | - | - |
      | operation | PATCH /company | one row updated | - | p95 under 200 ms | - |

      ## Security and privacy
      | Kind | Subject | Decision | Enforced in |
      |---|---|---|---|
      | authorisation | PATCH /company | only an owner of that company | the service, from the session |
      | rate limit | PATCH /company | 30 a minute per user | the API gateway |
      | personal data | contact phone | kept while the company exists, deleted with it | the companies table |

      ## Errors and resilience
      | Failure | The user sees | Retry and idempotency |
      |---|---|---|
      | the network is down | "Not saved, try again" next to Save | the same PATCH is safe to send again |

      ## State and offline
      | Screen | States | Kept where | Offline and reconnect |
      |---|---|---|---|
      | O-ST-01 | loading, saved, error | the form on the client | Save waits until the network is back |

      ## Accessibility and language
      | Screen | Labels and focus | Contrast and text size | Strings and locale |
      |---|---|---|---|
      | O-ST-01 | every field labelled; an error is tied to its field | the tokens; text at 200% | strings in the catalogue; the phone in the country's format |

      ## Observability
      | Signal | Kind | Shows |
      |---|---|---|
      | company.updated | log | a profile was saved, without the phone number |

      ## Configuration and delivery
      | Setting | Per environment | Deploy order |
      |---|---|---|
      | n/a | the feature adds no setting and no secret | |

      ## Test strategy
      | Level | What it tests | Where |
      |---|---|---|
      | unit | parsing and formatting the phone | src/company/phone.test.ts |
      """

  @R-117.1
  Rule: Every screen row and field of the approved design is traced to a rule, an API field and a building block

    @EX-117.1.1
    Scenario: A screen row the design does not trace and a field with no building block are refused
      Given the input file technical design contains:
        """
        # Design: FEAT-001 Company profile

        ```mermaid
        flowchart LR
          api[PATCH /company] --> db[(companies)]
        ```

        ## Design trace
        | Screen | Element | Rule | API field | Component |
        |---|---|---|---|---|
        | - | contact phone | R-001.2 | company.phone | - |

        ## Building blocks
        | Field | Kind | Standard | Library | Package | Source |
        |---|---|---|---|---|---|
        | n/a | the feature stores no value of its own | | | | |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        design row O-ST-01 (Company profile) is not traced
        """
      And the stdout output contains:
        """
        field "contact phone" has no building block
        """

    @EX-117.1.2
    Scenario: A complete technical design passes
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-001: design is fine
        """

    @EX-117.1.3
    Scenario: A phone number kept as free text is refused
      Given the input file technical design contains:
        """
        ## Building blocks
        | Field | Kind | Standard | Library | Package | Source |
        |---|---|---|---|---|---|
        | contact phone | text | free text, up to 40 characters | none | - | https://developer.mozilla.org/en-US/docs/Web/HTML/Element/input |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        "contact phone" is a phone number: its standard is E.164
        """

    @EX-117.1.4
    Scenario: The product analyst sees the screen rows and fields of the feature
      When alice runs design with:
        | key | value     |
        | arg | FEAT-001  |
        | arg | --screens |
      Then the command succeeds
      And the stdout output contains:
        """
        O-ST-01 Company profile: states loading, saved, error; fields name, contact phone
        """

  @R-117.2
  Rule: Every building block and every outside call points to documentation a reader can open

    @EX-117.2.1
    Scenario: A building block whose source is a version file is refused
      Given the input file technical design contains:
        """
        ## Building blocks
        | Field | Kind | Standard | Library | Package | Source |
        |---|---|---|---|---|---|
        | contact phone | phone | E.164 | libphonenumber-js | npm:libphonenumber-js | package.json |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        a version file is not documentation
        """

    @EX-117.2.2
    Scenario: An outside call with no evidence on record is refused
      Given the input file technical design contains:
        """
        ## External services
        | Service | Call | Quota | Cost | On failure |
        |---|---|---|---|---|
        | supabase | update the companies row | 500 requests a second | included in the plan | show "Not saved" and keep the form |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        the call to supabase has no evidence on record
        """

    @EX-117.2.3
    Scenario: The evidence for an outside call is the official page of the service
      Given the input file sources record contains:
        """
        [supabase]
        name = "Supabase"
        docs = "https://supabase.com/docs"
        """
      When alice runs docs with:
        | key | value                                   |
        | arg | FEAT-001                                |
        | arg | --service                               |
        | arg | supabase                                |
        | arg | --source                                |
        | arg | https://stackoverflow.com/questions/1   |
      Then the command fails with usage error
      And the stderr output contains:
        """
        is not on the official site of supabase (https://supabase.com/docs)
        """

    @EX-117.2.4
    Scenario: Evidence from the official page is recorded for the design
      Given the input file sources record contains:
        """
        [supabase]
        name = "Supabase"
        docs = "https://supabase.com/docs"
        """
      When alice runs docs with:
        | key | value                                                   |
        | arg | FEAT-001                                                |
        | arg | --service                                               |
        | arg | supabase                                                |
        | arg | --source                                                |
        | arg | https://supabase.com/docs/reference/javascript/update   |
      Then the command succeeds
      And the stdout output contains:
        """
        recorded: design evidence for supabase
        """

  @R-117.3
  Rule: Each query has an index, each endpoint an authorisation row and each screen its states

    @EX-117.3.1
    Scenario: A query without an index is refused
      Given the input file technical design contains:
        """
        ## Data and performance
        | Kind | Name | Detail | Index | Budget | Rollback |
        |---|---|---|---|---|---|
        | query | company by owner | where owner_id = ? | - | - | - |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        query "company by owner" has no index
        """

    @EX-117.3.2
    Scenario: An endpoint without an authorisation row is refused
      Given the input file technical design contains:
        """
        ## API contract
        | Endpoint | Request | Response | Version | Older clients |
        |---|---|---|---|---|
        | PATCH /company | name, phone in E.164 | 200 with the company | v1 | unchanged |

        ## Security and privacy
        | Kind | Subject | Decision | Enforced in |
        |---|---|---|---|
        | rate limit | PATCH /company | 30 a minute per user | the API gateway |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        endpoint PATCH /company has no authorisation row
        """

    @EX-117.3.3
    Scenario: A screen that does not list a state of its row is refused
      Given the input file technical design contains:
        """
        ## Design trace
        | Screen | Element | Rule | API field | Component |
        |---|---|---|---|---|
        | O-ST-01 Company profile | name | R-001.1 | company.name | TextField |
        | O-ST-01 Company profile | contact phone | R-001.2 | company.phone | PhoneInput |

        ## State and offline
        | Screen | States | Kept where | Offline and reconnect |
        |---|---|---|---|
        | O-ST-01 | loading, saved | the form on the client | Save waits until the network is back |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        screen O-ST-01 (Company profile) does not list its state "error"
        """

  @R-117.4
  Rule: A section that does not apply says why

    @EX-117.4.1
    Scenario: A feature with no screen and no data passes with a reason in every section
      Given the input file second state contains:
        """
        {"schema": 1, "feature": "FEAT-002", "kind": "feature", "title": "Error wording", "created_at": "2026-11-19T10:00:00+00:00",
         "phase": "system-map", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": false, "changes": [], "approvals": [], "technical_design": true}
        """
      And the input file second technical design contains:
        """
        # Design: FEAT-002 Error wording

        ```mermaid
        flowchart LR
          cli[Command] --> message[Error message]
        ```

        ## Design trace
        | Screen | Element | Rule | API field | Component |
        |---|---|---|---|---|
        | n/a | the feature has no screen and no field | | | |

        ## Building blocks
        | Field | Kind | Standard | Library | Package | Source |
        |---|---|---|---|---|---|
        | n/a | no value is stored or shown | | | | |

        ## External services
        | Service | Call | Quota | Cost | On failure |
        |---|---|---|---|---|
        | n/a | nothing outside the command is called | | | |

        ## Architecture
        | Piece | Layer | Path |
        |---|---|---|
        | n/a | the wording lives where the message already is | | |

        ## Patterns
        | Pattern | Example file | Use for |
        |---|---|---|
        | n/a | one string changes; no pattern to copy | | |

        ## API contract
        | Endpoint | Request | Response | Version | Older clients |
        |---|---|---|---|---|
        | n/a | the feature adds and changes no endpoint | | | |

        ## Data and performance
        | Kind | Name | Detail | Index | Budget | Rollback |
        |---|---|---|---|---|---|
        | n/a | no table, query or operation changes | | | | |

        ## Security and privacy
        | Kind | Subject | Decision | Enforced in |
        |---|---|---|---|
        | n/a | the wording changes no access and no data | | |

        ## Errors and resilience
        | Failure | The user sees | Retry and idempotency |
        |---|---|---|
        | n/a | the message is the only change | |

        ## State and offline
        | Screen | States | Kept where | Offline and reconnect |
        |---|---|---|---|
        | n/a | no state is kept | | |

        ## Accessibility and language
        | Screen | Labels and focus | Contrast and text size | Strings and locale |
        |---|---|---|---|
        | n/a | a command line message; no screen | | |

        ## Observability
        | Signal | Kind | Shows |
        |---|---|---|
        | n/a | nothing new to watch in production | | |

        ## Configuration and delivery
        | Setting | Per environment | Deploy order |
        |---|---|---|
        | n/a | no setting, no secret, no migration | | |

        ## Test strategy
        | Level | What it tests | Where |
        |---|---|---|
        | n/a | the scenarios cover the one message | | |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-002 |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-002: design is fine
        """

    @EX-117.4.2
    Scenario: An empty section without a reason is refused
      Given the input file technical design contains:
        """
        ## Observability
        | Signal | Kind | Shows |
        |---|---|---|
        | n/a | | |
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command fails with violations found
      And the stdout output contains:
        """
        Observability: the section holds no row; write its rows, or one row n/a with the reason it does not apply
        """

  @R-117.5
  Rule: The code, security and UI reviewers review this very design before the tasks are written

    @EX-117.5.1
    Scenario: The tasks gate waits for the design reviews
      When alice runs gate with:
        | key | value    |
        | arg | FEAT-001 |
        | arg | tasks    |
        | arg | --result |
        | arg | pass     |
      Then the command fails with usage error
      And the stderr output contains:
        """
        FEAT-001 has no design review by the security-reviewer
        """

    @EX-117.5.2
    Scenario: A review of another version of the design does not count
      Given the input file company code review contains:
        """
        # code-reviewer: design of FEAT-001

        Design: 0000000000000000000000000000000000000000000000000000000000000000
        Verdict: PASS
        """
      When alice runs gate with:
        | key | value    |
        | arg | FEAT-001 |
        | arg | tasks    |
        | arg | --result |
        | arg | pass     |
      Then the command fails with usage error
      And the stderr output contains:
        """
        reviews/design-code-reviewer.md reviewed another version of design.md
        """

  @R-117.6
  Rule: A building block that is not installed is one line the person types; an agent never installs it

    @EX-117.6.1
    Scenario: The implement gate names the install line of a missing library
      Given the input file feature file contains:
        """
        @FEAT-001
        Feature: Company profile
        """
      And the input file package manifest contains:
        """
        {"packageManager": "pnpm@9.0.0", "dependencies": {"next": "16.4.5"}}
        """
      When alice runs gate with:
        | key | value     |
        | arg | FEAT-001  |
        | arg | implement |
        | arg | --result  |
        | arg | pass      |
      Then the command fails with usage error
      And the stderr output contains:
        """
        libphonenumber-js (npm) is not a dependency of the project: the person types ! pnpm add libphonenumber-js
        """

    @EX-117.6.2
    Scenario: An agent may not install the library itself
      When alice runs guard with:
        | key   | value                                                                                         |
        | stdin | {"tool_name":"Bash","agent_type":"greenlight:implementer","tool_input":{"command":"pnpm add x"}} |
      Then the command fails with refused
      And the stderr output contains:
        """
        may not install packages
        """

  @R-117.7
  Rule: A feature started before the technical design keeps the gates it had

    @EX-117.7.1
    Scenario: A new feature's system map waits for a technical design
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs create feature with:
        | key | value     |
        | arg | FEAT-003  |
        | arg | --title   |
        | arg | Invoices  |
      And alice runs gate with:
        | key | value      |
        | arg | FEAT-003   |
        | arg | system-map |
        | arg | --result   |
        | arg | pass       |
      Then the command fails with usage error
      And the stderr output contains:
        """
        there is no design.md
        """

    @EX-117.7.2
    Scenario: A feature from before checks only its diagrams
      Given the input file company state contains:
        """
        {"schema": 1, "feature": "FEAT-001", "kind": "feature", "title": "Company profile", "created_at": "2026-11-01T10:00:00+00:00",
         "phase": "system-map", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "assumptions": [], "cost": {},
         "red": null, "hooks_seen": false, "changes": [], "approvals": []}
        """
      And the input file technical design contains:
        """
        # Design: FEAT-001 Company profile

        ```mermaid
        flowchart LR
          ui[Profile screen] --> api[PATCH /company]
        ```
        """
      When alice runs design with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-001: design view is fine
        """
