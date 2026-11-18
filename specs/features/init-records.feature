@FEAT-115
Feature: Setup records what the project already has
  When a person sets greenlight up, it reads the project's own files and writes down the services it uses, the quality
  tools it declares, its design folder and the surfaces it ships. Every later stage works from those records, not from a
  guess, and nothing the person wrote is ever overwritten.

  @R-115.1
  Rule: A dependency that names a known service becomes a source with its official documentation

    @EX-115.1.1
    Scenario: A Node project that uses Supabase and Stripe
      Given the input file package manifest contains:
        """
        {"dependencies": {"@supabase/supabase-js": "^2.45.0", "stripe": "17.0.0", "left-pad": "1.3.0"}}
        """
      When alice runs init with:
        | key | value           |
        | arg | --adapter       |
        | arg | ts-cucumber-js  |
      Then the command succeeds
      And the stdout output contains:
        """
        sources: supabase, stripe
        """
      And the output file sources record contains:
        """
        [supabase]
        name = "Supabase"
        docs = "https://supabase.com/docs"
        package = "@supabase/supabase-js"
        version = "^2.45.0"
        cli = "supabase"
        """

    @EX-115.1.2
    Scenario: A package nobody recognises is not guessed
      Given the input file package manifest contains:
        """
        {"dependencies": {"left-pad": "1.3.0"}}
        """
      When alice runs init with:
        | key | value           |
        | arg | --adapter       |
        | arg | ts-cucumber-js  |
      Then the command succeeds
      And the stdout output contains:
        """
        sources: none recognised
        """

  @R-115.2
  Rule: Only a tool the project itself declares becomes a quality check

    @EX-115.2.1
    Scenario: A Python project that declares ruff and mypy
      Given the input file python project contains:
        """
        [project]
        name = "shop"
        dependencies = []

        [dependency-groups]
        dev = ["ruff>=0.6", "mypy>=1.11"]
        """
      When alice runs init with:
        | key | value               |
        | arg | --adapter           |
        | arg | python-pytest-bdd   |
      Then the command succeeds
      And the stdout output contains:
        """
        quality: ruff, ruff-format, mypy
        """
      And the output file project config contains:
        """
        [adapters.quality.mypy]
        """

    @EX-115.2.2
    Scenario: A Go module gets its own toolchain checks and no linter it does not declare
      Given the input file go module contains:
        """
        module example.com/shop

        go 1.24
        """
      When alice runs init with:
        | key | value        |
        | arg | --adapter    |
        | arg | go-godog     |
      Then the command succeeds
      And the stdout output contains:
        """
        quality: gofmt, go-vet
        surfaces:
        """

    @EX-115.2.3
    Scenario: A Node project that declares only the TypeScript compiler
      Given the input file package manifest contains:
        """
        {"devDependencies": {"typescript": "5.6.0"}}
        """
      And the input file typescript config contains:
        """
        {"compilerOptions": {"strict": true}}
        """
      When alice runs init with:
        | key | value           |
        | arg | --adapter       |
        | arg | ts-cucumber-js  |
      Then the command succeeds
      And the stdout output contains:
        """
        quality: tsc
        surfaces:
        """

  @R-115.3
  Rule: A design folder with a system file or an inventory is recorded, and no folder records nothing

    @EX-115.3.1
    Scenario: A design folder
      Given the input file design system contains:
        """
        # Design system
        """
      And the input file design inventory contains:
        """
        # Inventory
        """
      And the input file design screen contains:
        """
        <html></html>
        """
      When alice runs init with:
        | key | value           |
        | arg | --adapter       |
        | arg | ts-cucumber-js  |
      Then the command succeeds
      And the stdout output contains:
        """
        design: design/DESIGN.md, design/screens/*, design/inventory.md
        """
      And the output file project config contains:
        """
        [design]
        system = "design/DESIGN.md"
        screens = "design/screens/*"
        inventory = "design/inventory.md"
        """

    @EX-115.3.2
    Scenario: No design folder
      Given the input file package manifest contains:
        """
        {"dependencies": {"express": "5.0.0"}}
        """
      When alice runs init with:
        | key | value           |
        | arg | --adapter       |
        | arg | ts-cucumber-js  |
      Then the command succeeds
      And the stdout output contains:
        """
        design: none found
        """

  @R-115.4
  Rule: Every surface the product ships is listed, and one no adapter can check is recorded as unverified

    @EX-115.4.1
    Scenario: An Expo app has mobile screens no adapter checks
      Given the input file package manifest contains:
        """
        {"dependencies": {"expo": "~52.0.0", "react-native": "0.76.0"}}
        """
      When alice runs init with:
        | key | value           |
        | arg | --adapter       |
        | arg | ts-cucumber-js  |
      Then the command succeeds
      And the stdout output contains:
        """
        mobile screens: no adapter, recorded as unverified
        """
      And the output file project config contains:
        """
        [surfaces]
        ios = "unverified"
        android = "unverified"
        """

    @EX-115.4.2
    Scenario: A web app names the adapter that could check its screens
      Given the input file package manifest contains:
        """
        {"dependencies": {"next": "15.0.0", "react": "19.0.0"}}
        """
      When alice runs init with:
        | key | value           |
        | arg | --adapter       |
        | arg | ts-cucumber-js  |
      Then the command succeeds
      And the stdout output contains:
        """
        web screens: not checked by ts-cucumber-js; ts-playwright-bdd covers web
        """

  @R-115.5
  Rule: Running the records again adds what is new and keeps what the person wrote

    @EX-115.5.1
    Scenario: A source the person edited is kept
      Given the input file package manifest contains:
        """
        {"dependencies": {"stripe": "17.0.0", "@sentry/node": "8.0.0"}}
        """
      And the input file project config contains:
        """
        autonomy = "guided"
        """
      And the input file sources record contains:
        """
        [stripe]
        name = "Stripe (our wording)"
        docs = "https://docs.stripe.com/our-page"
        """
      When alice runs refresh the records
      Then the command succeeds
      And the output file sources record contains:
        """
        name = "Stripe (our wording)"
        """
      And the output file sources record contains:
        """
        [sentry]
        """

  @R-115.6
  Rule: The status of a project says which surfaces are unverified

    @EX-115.6.1
    Scenario: A recorded surface without an adapter
      Given the input file project config contains:
        """
        autonomy = "guided"

        [surfaces]
        ios = "unverified"
        """
      When alice runs status
      Then the command succeeds
      And the stdout output contains:
        """
        unverified surfaces: ios
        """
