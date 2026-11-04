@FEAT-105
Feature: Adding an adapter writes its files under the names the project needs
  Some files an adapter brings must have an exact name in the project, such as the lock file that .NET checks package
  hashes against. Company security tools can block a program from touching a file with that name, so greenlight ships
  such a file with a ".template" ending and gives it its real name only when the adapter is added to a project.

  @R-105.1
  Rule: A file shipped with a ".template" ending is written without that ending

    @EX-105.1.1
    Scenario: The .NET lock file gets the name that .NET reads
      Given the input file project config contains:
        """
        # greenlight project settings
        """
      When alice runs add the .NET adapter
      Then the command succeeds
      And the output file .NET lock file contains:
        """
        "contentHash"
        """
      And the stdout output contains:
        """
        + tests/packages.lock.json
          + tests/run_dotnet.py
        """

  @R-105.2
  Rule: The Node adapters pin their tooling with pnpm

    @EX-105.2.1
    Scenario: The Node adapter brings a pnpm lock file
      Given the input file project config contains:
        """
        # greenlight project settings
        """
      When alice runs add the Node adapter
      Then the command succeeds
      And the output file Node lock file contains:
        """
        lockfileVersion
        """
      And the stdout output contains:
        """
        + tests/pnpm-lock.yaml
        """
