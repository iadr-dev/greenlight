@FEAT-110
Feature: The guard refuses what weakens greenlight and nothing else
  The guard refuses a tool call that would change what enforces greenlight, a locked or managed file, or the project's
  environment. In the Fieldly run it also refused ordinary work: the bdd command line run by its plugin path, a quoted
  argument or a regular expression read as a write or a file pattern, a new file that shares a name with a locked one,
  a script in the temp folder, a memory note, a type check and a harmless settings change. Each of those is now let
  through, and each protection still holds.

  Background:
    Given the input file project config contains:
      """
      [[adapters]]
      name = "x"
      features = "tests/features"
      steps = "tests/drivers"
      """

  @R-110.1
  Rule: Only what a command writes to counts, not its quoted arguments or its patterns

    @EX-110.1.1
    Scenario: The bdd command line run by its plugin path with a quoted argument is not a write
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "tool_input": {
          "command": "sh \"plugin/tools/bdd/bdd\" assume FEAT-007 --text \"Keep state.json\" --alt \"Move it\" > out.txt"}}
        """
      When alice runs the guard on the hook payload with:
        | key                    | value  |
        | env.CLAUDE_PLUGIN_ROOT | plugin |
      Then the command succeeds

    @EX-110.1.2
    Scenario: A regular expression in a script that edits a production file is not a file pattern
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "agent_type": "greenlight:implementer", "tool_input": {
          "command": "python -c \"import re; t=open('a.py').read(); open('a.py','w').write(re.sub(r' .*?', '', t))\""}}
        """
      When alice runs the guard on the hook payload
      Then the command succeeds

    @EX-110.1.3
    Scenario: A command that writes into the plugin is still refused
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "tool_input": {"command": "cp evil.sh \"plugin/tools/bdd/bdd\""}}
        """
      When alice runs the guard on the hook payload with:
        | key                    | value  |
        | env.CLAUDE_PLUGIN_ROOT | plugin |
      Then the command fails with refused
      And the stderr output contains:
        """
        part of what enforces greenlight
        """

  @R-110.2
  Rule: A locked file is matched by its path, not by its name anywhere in the command

    @EX-110.2.1
    Scenario: A production file that shares its name with a locked driver can be written
      Given the input file locked driver contains:
        """
        export const barrier = 1;
        """
      And the input file lock record contains:
        """
        {"schema": 1, "feature": "FEAT-007", "history": [],
         "scopes": {"bind": {"locked_at": "2026-01-01T00:00:00+00:00",
                             "files": {"tests/drivers/barrier.ts": "00"}}}}
        """
      And the input file hook payload contains:
        """
        {"tool_name": "Bash", "agent_type": "greenlight:implementer", "tool_input": {
          "command": "cat > api/src/ports/barrier.ts <<'EOF'\nexport {};\nEOF"}}
        """
      When alice runs the guard on the hook payload
      Then the command succeeds

    @EX-110.2.2
    Scenario: The locked driver itself is still refused
      Given the input file locked driver contains:
        """
        export const barrier = 1;
        """
      And the input file lock record contains:
        """
        {"schema": 1, "feature": "FEAT-007", "history": [],
         "scopes": {"bind": {"locked_at": "2026-01-01T00:00:00+00:00",
                             "files": {"tests/drivers/barrier.ts": "00"}}}}
        """
      And the input file hook payload contains:
        """
        {"tool_name": "Bash", "agent_type": "greenlight:implementer", "tool_input": {
          "command": "cd tests && sed -i s/1/2/ drivers/barrier.ts"}}
        """
      When alice runs the guard on the hook payload
      Then the command fails with refused
      And the stderr output contains:
        """
        tests/drivers/barrier.ts is locked by FEAT-007 (bind)
        """

  @R-110.3
  Rule: A script in the temp folder and a memory note are not project files

    @EX-110.3.1
    Scenario: An agent writes a script in the temp folder outside every project
      Given the input file hook payload contains:
        """
        {"tool_name": "Write", "agent_type": "greenlight:qa-designer", "tool_input": {"file_path": "../scratch/apply.py"}}
        """
      When alice runs the guard on the hook payload
      Then the command succeeds

    @EX-110.3.2
    Scenario: A memory note under the Claude Code projects folder can be saved
      Given the input file hook payload contains:
        """
        {"tool_name": "Write", "tool_input": {"file_path": "claude-home/projects/p/memory/notes.md"}}
        """
      When alice runs the guard on the hook payload with:
        | key                   | value       |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      Then the command succeeds

    @EX-110.3.3
    Scenario: A session transcript is still refused
      Given the input file hook payload contains:
        """
        {"tool_name": "Write", "tool_input": {"file_path": "claude-home/projects/p/s.jsonl"}}
        """
      When alice runs the guard on the hook payload with:
        | key                   | value       |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      Then the command fails with refused
      And the stderr output contains:
        """
        session transcript
        """

  @R-110.4
  Rule: Running a tool that is already installed is not installing one

    @EX-110.4.1
    Scenario: A reviewer type-checks with the installed compiler
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "agent_type": "greenlight:code-reviewer", "tool_input": {
          "command": "npx --no-install tsc -p tsconfig.json --noEmit > tc.txt; grep -ciE \"pnpm|npx\" tc.txt"}}
        """
      When alice runs the guard on the hook payload
      Then the command succeeds

    @EX-110.4.2
    Scenario: Adding a package is still refused
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "agent_type": "greenlight:implementer", "tool_input": {"command": "pnpm add left-pad"}}
        """
      When alice runs the guard on the hook payload
      Then the command fails with refused
      And the stderr output contains:
        """
        may not install packages
        """

  @R-110.5
  Rule: A settings change is judged by what it changes

    @EX-110.5.1
    Scenario: Claude adds an environment variable to the project settings
      Given the input file project settings contains:
        """
        {"permissions": {"allow": ["Bash(ls:*)"]}}
        """
      And the input file hook payload contains:
        """
        {"tool_name": "Write", "tool_input": {"file_path": ".claude/settings.json",
          "content": "{\"permissions\": {\"allow\": [\"Bash(ls:*)\"]}, \"env\": {\"TEST_DATABASE_URL\": \"sqlite://\"}}"}}
        """
      When alice runs the guard on the hook payload
      Then the command succeeds

    @EX-110.5.2
    Scenario: Turning the hooks off is still refused
      Given the input file project settings contains:
        """
        {"permissions": {"allow": ["Bash(ls:*)"]}}
        """
      And the input file hook payload contains:
        """
        {"tool_name": "Edit", "tool_input": {"file_path": ".claude/settings.json",
          "old_string": "\"permissions\"", "new_string": "\"disableAllHooks\": true, \"permissions\""}}
        """
      When alice runs the guard on the hook payload
      Then the command fails with refused
      And the stderr output contains:
        """
        disableAllHooks
        """

    @EX-110.5.3
    Scenario: Hooks written with an escaped key are still refused
      Given the input file hook payload contains:
        """
        {"tool_name": "Write", "tool_input": {"file_path": ".claude/settings.local.json",
          "content": "{\"hoo\\u006bs\": {}}"}}
        """
      When alice runs the guard on the hook payload
      Then the command fails with refused
      And the stderr output contains:
        """
        hooks
        """

    @EX-110.5.4
    Scenario: A shell command that writes the settings is still refused
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "tool_input": {"command": "echo '{\"env\": {}}' > .claude/settings.json"}}
        """
      When alice runs the guard on the hook payload
      Then the command fails with refused
      And the stderr output contains:
        """
        part of what enforces greenlight
        """

  @R-110.6
  Rule: The person adds the recommended deny rules with one typed line

    @EX-110.6.1
    Scenario: The line adds the missing rules and keeps everything else in the settings
      Given the input file project settings contains:
        """
        {"env": {"TEST_DATABASE_URL": "sqlite://"}, "permissions": {"deny": ["Bash(rm -rf:*)"]}}
        """
      When alice runs doctor with:
        | key | value            |
        | arg | --add-deny-rules |
      Then the stdout output contains:
        """
        added 7 deny rule(s) to .claude/settings.json
        """
      And the output file project settings contains:
        """
        "TEST_DATABASE_URL": "sqlite://"
        """
      And the output file project settings contains:
        """
        "Bash(rm -rf:*)"
        """
      And the output file project settings contains:
        """
        "Write(**/.bdd/**/state.json)"
        """

    @EX-110.6.2
    Scenario: Typing the line again changes nothing
      When alice runs doctor with:
        | key | value            |
        | arg | --add-deny-rules |
      And alice runs doctor with:
        | key | value            |
        | arg | --add-deny-rules |
      Then the stdout output contains:
        """
        every recommended deny rule is already in .claude/settings.json
        """

    @EX-110.6.3
    Scenario: The same line run from a tool call is refused
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "tool_input": {"command": "sh \"plugin/tools/bdd/bdd\" doctor --add-deny-rules"}}
        """
      When alice runs the guard on the hook payload
      Then the command fails with refused
      And the stderr output contains:
        """
        the person's act
        """

  @R-110.7
  Rule: An agent neither corrects the recorded costs nor releases the shared test plumbing

    @EX-110.7.1
    Scenario: An agent's cost correction is refused
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "agent_type": "greenlight:implementer", "tool_input": {
          "command": "bdd cost FEAT-007 --amend implement --tokens 1 --seconds 1 --reason x"}}
        """
      When alice runs the guard on the hook payload
      Then the command fails with refused
      And the stderr output contains:
        """
        cost corrections are made by the person or the orchestrator
        """

    @EX-110.7.2
    Scenario: An agent's release of the shared test plumbing is refused
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "agent_type": "greenlight:step-engineer", "tool_input": {
          "command": "bdd unlock --plumbing --reason x"}}
        """
      When alice runs the guard on the hook payload
      Then the command fails with refused
      And the stderr output contains:
        """
        the person or the orchestrator releases it
        """

    @EX-110.7.3
    Scenario: The orchestrator may correct a cost
      Given the input file hook payload contains:
        """
        {"tool_name": "Bash", "tool_input": {
          "command": "bdd cost FEAT-007 --amend implement --tokens 1 --seconds 1 --reason x"}}
        """
      When alice runs the guard on the hook payload
      Then the command succeeds
