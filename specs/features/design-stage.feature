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

        Design: bd269d555e7bd88b33ad877353401c277ccaef08657794f0c49d151e20e7d2d8
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
      And alice runs the design review by the ui-reviewer
      And alice runs gallery
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
    Scenario: The orchestrator may not change an approved screen
      Given the input file design review contains:
        """
        Design: bd269d555e7bd88b33ad877353401c277ccaef08657794f0c49d151e20e7d2d8
        Verdict: PASS
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the design review by the ui-reviewer
      And alice runs gallery
      And alice runs the approval hook with:
        | key   | value                                                                               |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve design"} |
      And alice runs guard with:
        | key   | value                                                                     |
        | stdin | {"tool_name":"Edit","tool_input":{"file_path":"design/screens/home.html"}} |
      Then the command fails with refused
      And the stderr output contains:
        """
        design/screens/home.html is part of the approved product design, locked by the project
        """

    @EX-116.5.2
    Scenario: The implementer may not add a file to the approved design folder
      Given the input file design review contains:
        """
        Design: bd269d555e7bd88b33ad877353401c277ccaef08657794f0c49d151e20e7d2d8
        Verdict: PASS
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the design review by the ui-reviewer
      And alice runs gallery
      And alice runs the approval hook with:
        | key   | value                                                                               |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve design"} |
      And alice runs guard with:
        | key   | value                                                                                         |
        | stdin | {"tool_name":"Edit","agent_type":"greenlight:implementer","tool_input":{"file_path":"design/x.md"}} |
      Then the command fails with refused
      And the stderr output contains:
        """
        design/x.md is part of the approved product design, locked by the project
        """

  @R-116.6
  Rule: A change to the approved design releases the lock, revokes the approval and shows the person only what changed

    @EX-116.6.1
    Scenario: Reopening the design releases the lock and revokes the approval
      Given the input file design review contains:
        """
        Design: bd269d555e7bd88b33ad877353401c277ccaef08657794f0c49d151e20e7d2d8
        Verdict: PASS
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs the design review by the ui-reviewer
      And alice runs gallery
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
        {"schema": 1, "started_at": "2026-11-19T12:06:29+00:00", "spec": "product-spec.md",
         "folder": "design", "history": [],
         "approvals": [{"id": 1, "gate": "design", "decision": "approve", "grade": "hook", "origin": "human",
           "at": "2026-11-19T12:06:30+00:00", "reason": "", "session": null, "prompt_id": "p",
           "transcript_path": "s.jsonl", "mode": "auto",
           "outside": [
            "b4b5940781ad", "3090b9e33386", "12af00ef4bee", "2ca1c1709e18", "f948f42761f4", "12af00ef4bee"],
           "artifacts": {
            ".bdd/architecture.md":
             "ecb6cec5db8e32adcfd101e74751d54e05e00c59d36e7808eb61b547acf99fc2",
            ".bdd/product.md":
             "c9783d8dda28045a14e7d841e7a65549ebff763ec2e7215c822461d889fc0c34",
            "design/DESIGN.md":
             "27bfa07c9ae7b15bb559ede4b112f51075ed9cfc1ead8c404c992977dc48ee45",
            "design/PRODUCT.md":
             "46cfddaac2d280557da5b404e9a0401c07414d0c44d0dc61aead9af1b43385ee",
            "design/flows.html":
             "cb1e40ba9e13c60fe942311f898f3c4a8b0041796a73d7e63899b2d2be3548fc",
            "design/inventory.md":
             "c82b60f97a147bc2ceb85ec0fba7461c6f3be1c297e8421463ae2e4a3a415375",
            "design/screens/home.html":
             "65d604a1bada408442e7a327a62b805cd52e4e6f5b6fa5858ee1553707258ab8",
            "design/tokens.css":
             "f9c46f5d9cc621cca65083c131bc0c403a9601aaad3ec39c02f66dbe0fd2b407",
            "design/tokens.json":
             "35e231bdc9cc333f30d3343f06d46d162b0bcbeb0e4e952a183f0a8181c1d2af"},
           "items": {
            "Architecture: Authentication": {"text": "Email magic link; sessions in an http-only cookie.",
             "parts": {"all": "249397bac59cde5b"}},
            "Architecture: CI and delivery":
             {"text": "Tests and the quality checks on every pull request; deploy on merge.",
             "parts": {"all": "e4c6e5281514164b"}},
            "Architecture: Data store": {"text": "Postgres.",
             "parts": {"all": "365fa5b238cf3428"}},
            "Architecture: Hosting and environments":
             {"text": "Vercel; preview per pull request, one production.",
             "parts": {"all": "ef9a297bcc3d6a89"}},
            "Architecture: Layers":
             {"text": "Pages call a service layer; the service layer calls the data store.",
             "parts": {"all": "84fe9ccdbb987b0f"}},
            "Architecture: Observability": {"text": "Structured logs and error tracking.",
             "parts": {"all": "22c6341914a440dc"}},
            "Architecture: Security baseline and threat model": {"text": "(a table)",
             "parts": {"all": "274bec494e445e28"}},
            "Architecture: Stack per surface": {"text": "(a table)",
             "parts": {"all": "3527c52c89ed93b3"}},
            "FEAT-001": {"text": "Sign in: A shopper signs in with their email.",
             "parts": {"all": "0e31e564287f6e43", "depends": "e3b0c44298fc1c14",
              "order": "6b86b273ff34fce1"}},
            "FEAT-002": {"text": "Orders: A signed-in shopper places an order and sees it in the list.",
             "parts": {"all": "03a08f96825519b9", "depends": "b97525dacc3d9d66",
              "order": "d4735e3a265e16ee"}},
            "S-IN-01": {"text": "Sign in",
             "parts": {"all": "239a01275968fd16", "feature": "b97525dacc3d9d66",
              "file": "1ff037f2c94f4da1", "states": "63f23f1c97754f97"}},
            "S-OR-01": {"text": "Order list",
             "parts": {"all": "8afc6a3bf5c6f7c4", "feature": "e907e450c06d0f3a",
              "file": "1ff037f2c94f4da1", "states": "63f23f1c97754f97"}},
            "design/DESIGN.md": {"text": "design file",
             "parts": {"all": "c86f0b57216d9d62", "content": "c86f0b57216d9d62"}},
            "design/PRODUCT.md": {"text": "design file",
             "parts": {"all": "52f3c4f08d2177f1", "content": "52f3c4f08d2177f1"}},
            "design/flows.html": {"text": "design file",
             "parts": {"all": "cd34c7f061465542", "content": "cd34c7f061465542"}},
            "design/screens/home.html": {"text": "screen file",
             "parts": {"all": "acaf87373be50be9", "content": "acaf87373be50be9"}},
            "design/tokens.css": {"text": "design file",
             "parts": {"all": "103951ee56ff89b0", "content": "103951ee56ff89b0"}},
            "design/tokens.json": {"text": "design file",
             "parts": {"all": "de106e7b064da7ea", "content": "de106e7b064da7ea"}}}}]}
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

  @R-116.7
  Rule: Where the hooks run, the design review counts only as the ui-reviewer wrote it

    @EX-116.7.1
    Scenario: The orchestrator may not write the design review
      When alice runs guard with:
        | key   | value                                                                                    |
        | stdin | {"tool_name":"Edit","tool_input":{"file_path":".bdd/design-reviews/design-ui-reviewer.md"}} |
      Then the command fails with refused
      And the stderr output contains:
        """
        only the ui-reviewer agent writes it
        """

    @EX-116.7.2
    Scenario: A design review the ui-reviewer did not write does not let the person approve
      Given the input file design review contains:
        """
        Design: bd269d555e7bd88b33ad877353401c277ccaef08657794f0c49d151e20e7d2d8
        Verdict: PASS
        """
      When alice runs init with:
        | key | value            |
        | arg | --product        |
        | arg | product-spec.md  |
      And alice runs gallery
      And alice runs the approval hook with:
        | key   | value                                                                               |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve design"} |
      Then the command succeeds
      And the stdout output contains:
        """
        is not what the ui-reviewer agent wrote
        """
