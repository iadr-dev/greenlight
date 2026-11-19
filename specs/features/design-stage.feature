@FEAT-116
Feature: A product design the person approves by looking
  A person who has only a product spec gets, once for the whole product, a description of who uses it, a feature map,
  the architecture decisions and a complete visual design: every screen as real HTML with every state, the flows and
  the tokens. They approve it by looking at one gallery page. After the approval the design is locked, so the code is
  built against what the person saw, and a change to it goes back through the person.

  Background:
    Given the input file project config contains:
      """
      [[adapters]]
      name = "x"
      features = "features"
      steps = "steps"

      [design]
      system = "design/DESIGN.md"
      screens = "design/screens/*"
      inventory = "design/inventory.md"
      """
    And the input file product spec contains:
      """
      A small shop. Shoppers sign in and place orders from the web.
      """
    And the input file product description contains:
      """
      # Shop

      ## Users
      Shoppers who buy from a small shop.

      ## Jobs
      Sign in, then place an order and see it in the list.

      ## Platforms
      web
      """
    And the input file product map contains:
      """
      # Product map

      | ID | Feature | Description | Depends on | Order |
      |---|---|---|---|---|
      | FEAT-001 | Sign in | A shopper signs in with their email. | - | 1 |
      | FEAT-002 | Orders | A signed-in shopper places an order and sees it in the list. | FEAT-001 | 2 |
      """
    And the input file architecture contains:
      """
      # Architecture

      ## Stack per surface
      | Surface | Stack |
      |---|---|
      | web | Next.js 16 with TypeScript |

      ## Layers
      Pages call a service layer; the service layer calls the data store.

      ## Hosting and environments
      Vercel; preview per pull request, one production.

      ## Authentication
      Email magic link; sessions in an http-only cookie.

      ## Data store
      Postgres.

      ## Security baseline and threat model
      | Threat | Control |
      |---|---|
      | Stolen session | http-only, secure cookie; rotation at sign-in |

      ## Observability
      Structured logs and error tracking.

      ## CI and delivery
      Tests and the quality checks on every pull request; deploy on merge.
      """
    And the input file design system contains:
      """
      # Shop design

      ## Design contract
      Shoppers come back to their orders: the order list is the first thing they read.
      """
    And the input file design tokens contains:
      """
      {"color": {"primary": "#137547", "text": "#15201A"}, "space": {"2": "8px"}}
      """
    And the input file design token styles contains:
      """
      :root { --primary: #137547; --text: #15201A; --space-2: 8px; }
      """
    And the input file design flows contains:
      """
      <!doctype html>
      <html><body><h1>Flows</h1><ol data-flow="order"><li>S-IN-01</li><li>S-OR-01</li></ol></body></html>
      """
    And the input file design inventory contains:
      """
      # Screen inventory

      | ID | Screen | States | Feature | File |
      |---|---|---|---|---|
      | S-IN-01 | Sign in | loading, error, success | FEAT-001 | screens/home.html |
      | S-OR-01 | Order list | loading, empty, error, success | FEAT-002 | screens/home.html |
      """
    And the input file design screen contains:
      """
      <!doctype html>
      <html><head><link rel="stylesheet" href="../tokens.css"></head><body>
      <section data-screen="S-IN-01" data-state="loading"><h2>Signing you in</h2></section>
      <section data-screen="S-IN-01" data-state="error"><h2>That link has expired</h2></section>
      <section data-screen="S-IN-01" data-state="success"><h2>Welcome back</h2></section>
      <section data-screen="S-OR-01" data-state="loading"><h2>Loading your orders</h2></section>
      <section data-screen="S-OR-01" data-state="empty"><h2>No orders yet</h2></section>
      <section data-screen="S-OR-01" data-state="error"><h2>Orders could not load</h2></section>
      <section data-screen="S-OR-01" data-state="success"><h2>Your orders</h2></section>
      </body></html>
      """

  @R-116.1
  Rule: The design stage starts from a product spec and adds no gate to a project that never starts it

    @EX-116.1.1
    Scenario: Starting from a product spec records the stage and keeps what the person already wrote
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      Then the command succeeds
      And the stdout output contains:
        """
        design stage: started from product-spec.md
        """
      And the output file design record contains:
        """
        "spec": "product-spec.md"
        """
      And the output file product map contains:
        """
        | FEAT-002 | Orders |
        """

    @EX-116.1.2
    Scenario: A project that never started the stage starts a feature without a design gate
      When alice runs create feature with:
        | key | value    |
        | arg | FEAT-001 |
        | arg | --title  |
        | arg | Sign in  |
      And alice runs gate with:
        | key | value    |
        | arg | FEAT-001 |
        | arg | discover |
        | arg | --result |
        | arg | pass     |
      Then the command succeeds

    @EX-116.1.3
    Scenario: Once the stage is started, a feature waits for the approved design
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs create feature with:
        | key | value    |
        | arg | FEAT-001 |
        | arg | --title  |
        | arg | Sign in  |
      And alice runs gate with:
        | key | value    |
        | arg | FEAT-001 |
        | arg | discover |
        | arg | --result |
        | arg | pass     |
      Then the command fails with usage error
      And the stderr output contains:
        """
        the product design is not approved yet
        """

  @R-116.2
  Rule: The gallery shows every screen and state of the design, grouped by feature, on one page that needs no network

    @EX-116.2.1
    Scenario: The gallery of a complete design
      When alice runs gallery
      Then the command succeeds
      And the stdout output contains:
        """
        design/gallery.html: 2 screens, 7 states, 2 features
        """
      And the output file gallery contains:
        """
        <h2 id="FEAT-002">FEAT-002 Orders</h2>
        """
      And the output file gallery contains:
        """
        data-row="S-OR-01"
        """

  @R-116.3
  Rule: The design checks name every gap between the inventory, the screens, the product map and the architecture

    @EX-116.3.1
    Scenario: A screen that does not show a state its row lists
      Given the input file design screen contains:
        """
        <!doctype html>
        <html><head><link rel="stylesheet" href="../tokens.css"></head><body>
        <section data-screen="S-IN-01" data-state="loading"></section>
        <section data-screen="S-IN-01" data-state="error"></section>
        <section data-screen="S-IN-01" data-state="success"></section>
        <section data-screen="S-OR-01" data-state="loading"></section>
        <section data-screen="S-OR-01" data-state="error"></section>
        <section data-screen="S-OR-01" data-state="success"></section>
        </body></html>
        """
      When alice runs gallery with:
        | key | value   |
        | arg | --check |
      Then the command fails with violations found
      And the stdout output contains:
        """
        S-OR-01 lists the state empty, but screens/home.html shows no data-state="empty" for it
        """

    @EX-116.3.2
    Scenario: A row that names a feature the product map does not have
      Given the input file design inventory contains:
        """
        | ID | Screen | States | Feature | File |
        |---|---|---|---|---|
        | S-IN-01 | Sign in | loading, error, success | FEAT-001 | screens/home.html |
        | S-OR-01 | Order list | loading, empty, error, success | FEAT-009 | screens/home.html |
        """
      When alice runs gallery with:
        | key | value   |
        | arg | --check |
      Then the command fails with violations found
      And the stdout output contains:
        """
        S-OR-01 names FEAT-009, which the product map (.bdd/product.md) does not list
        """

    @EX-116.3.3
    Scenario: An architecture without its security section
      Given the input file architecture contains:
        """
        # Architecture

        ## Stack per surface
        | Surface | Stack |
        |---|---|
        | web | Next.js 16 with TypeScript |

        ## Layers
        Pages call a service layer.

        ## Hosting and environments
        Vercel.

        ## Authentication
        Email magic link.

        ## Data store
        Postgres.

        ## Observability
        Structured logs.

        ## CI and delivery
        Tests on every pull request.
        """
      When alice runs gallery with:
        | key | value   |
        | arg | --check |
      Then the command fails with violations found
      And the stdout output contains:
        """
        the architecture has no "Security baseline and threat model" section
        """

  @R-116.4
  Rule: Only the person approves the design, by typing the approval alone, after the ui-reviewer has reviewed it

    @EX-116.4.1
    Scenario: An approval before the design review is not recorded
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the approval hook with:
        | key   | value                                                                               |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve design"} |
      Then the command succeeds
      And the stdout output contains:
        """
        NOT recorded. cannot approve the design: the ui-reviewer has not reviewed it yet
        """

    @EX-116.4.2
    Scenario: The person's approval is verified against the transcript and locks the design
      Given the input file design review contains:
        """
        # Design review

        Design: DIGEST
        Verdict: PASS
        """
      And the input file acknowledging session transcript contains:
        """
        {"type":"user","promptId":"p","origin":{"kind":"human"},"message":{"content":"/greenlight:approve design"}}
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the approval hook with:
        | key   | value                                                                               |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve design"} |
      And alice runs approve with:
        | key                   | value       |
        | arg                   | design      |
        | arg                   | --verify    |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      And alice runs status
      Then the command succeeds
      And the stdout output contains:
        """
        design: approved, locked
        """

    @EX-116.4.3
    Scenario: A self-reported design approval is refused under hard enforcement
      Given the input file project config contains:
        """
        enforcement = "hard"

        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"

        [design]
        system = "design/DESIGN.md"
        screens = "design/screens/*"
        inventory = "design/inventory.md"
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs approve with:
        | key | value           |
        | arg | design          |
        | arg | --self-reported |
      Then the command fails with usage error
      And the stderr output contains:
        """
        a self-reported approval is not accepted: this project requires hard enforcement
        """

    @EX-116.4.4
    Scenario: A design approval with other text in the message is not recorded
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the approval hook with:
        | key   | value                                                             |
        | stdin | {"prompt":"/greenlight:approve design looks great"}                |
      Then the command succeeds
      And the stdout output contains:
        """
        NOT recorded: send one approval per message
        """

  @R-116.5
  Rule: The approved design, the product map and the architecture are locked against every agent

    @EX-116.5.1
    Scenario: The implementer may not change an approved screen
      Given the input file design review contains:
        """
        Design: DIGEST
        Verdict: PASS
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the approval hook with:
        | key   | value                                                                               |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve design"} |
      And alice runs guard with:
        | key   | value                                                                                                              |
        | stdin | {"tool_name":"Write","agent_type":"greenlight:implementer","tool_input":{"file_path":"design/screens/home.html"}} |
      Then the command fails with refused
      And the stderr output contains:
        """
        design/screens/home.html is part of the approved product design, locked by the project
        """

    @EX-116.5.2
    Scenario: A new screen may not be added to the approved design folder
      Given the input file design review contains:
        """
        Design: DIGEST
        Verdict: PASS
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the approval hook with:
        | key   | value                                                                               |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve design"} |
      And alice runs guard with:
        | key   | value                                                                         |
        | stdin | {"tool_name":"Write","tool_input":{"file_path":"design/screens/checkout.html"}} |
      Then the command fails with refused
      And the stderr output contains:
        """
        design/screens/checkout.html is part of the approved product design, locked by the project
        """

  @R-116.6
  Rule: A change to the approved design releases the lock, revokes the approval and shows the person only what changed

    @EX-116.6.1
    Scenario: Reopening the design releases the lock and revokes the approval
      Given the input file design review contains:
        """
        Design: DIGEST
        Verdict: PASS
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the approval hook with:
        | key   | value                                                                               |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve design"} |
      And alice runs change with:
        | key | value                         |
        | arg | --reopen                      |
        | arg | design                        |
        | arg | --reason                      |
        | arg | the order list needs a filter |
      Then the command succeeds
      And the stdout output contains:
        """
        design reopened (the order list needs a filter): the lock is released and the approval is revoked
        """
      And the output file design lock record contains:
        """
        "reason": "the order list needs a filter"
        """

    @EX-116.6.2
    Scenario: After a change the summary shows only the screen that changed
      Given the input file design record contains:
        """
        RECORD
        """
      When alice runs approve with:
        | key | value     |
        | arg | design    |
        | arg | --summary |
      Then the command succeeds
      And the stdout output contains:
        """
        Changed:
          S-OR-01  Order list
        """
