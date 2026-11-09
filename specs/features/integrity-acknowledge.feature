@FEAT-109
Feature: The integrity check does not block ordinary changes
  The integrity check reports a change to what enforces greenlight, made during a tool call, and the implement and
  verify gates refuse while one is open. Updating the plugin, setting the project up and the person's own changes are
  not such changes. When something is open that the person made or accepts, the person says so by typing the approval
  command, and nothing an agent runs can do it for them.

  @R-109.1
  Rule: A plugin update Claude Code installed is taken at the next prompt instead of one violation per file

    @EX-109.1.1
    Scenario: A new plugin version Claude Code installed is recorded as an update at the next prompt
      Given the input file plugin manifest contains:
        """
        {"name": "greenlight", "version": "1.2.1"}
        """
      And the input file updated plugin manifest contains:
        """
        {"name": "greenlight", "version": "1.2.2"}
        """
      And the input file Claude Code plugin record contains:
        """
        {"plugins":{"greenlight@gl":[{"installPath":"claude-home/plugins/cache/gl/greenlight/1.2.2","version":"1.2.2"}]}}
        """
      And the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs the prompt check with:
        | key                    | value       |
        | stdin                  | {}          |
        | env.CLAUDE_PLUGIN_ROOT | plugin      |
        | env.CLAUDE_CONFIG_DIR  | claude-home |
      And alice runs the prompt check with:
        | key                    | value                                         |
        | stdin                  | {}                                            |
        | env.CLAUDE_PLUGIN_ROOT | claude-home/plugins/cache/gl/greenlight/1.2.2 |
        | env.CLAUDE_CONFIG_DIR  | claude-home                                   |
      And alice runs doctor with:
        | key                   | value       |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      Then the stdout output contains:
        """
        integrity: plugin updated from 1.2.1 to 1.2.2; baseline refreshed
        """

    @EX-109.1.2
    Scenario: A plugin file that differs under the same version is still a violation
      Given the input file plugin manifest contains:
        """
        {"name": "greenlight", "version": "1.2.1"}
        """
      And the input file plugin guard contains:
        """
        allowed = False
        """
      And the input file copied plugin manifest contains:
        """
        {"name": "greenlight", "version": "1.2.1"}
        """
      And the input file copied plugin guard contains:
        """
        allowed = True
        """
      And the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs the prompt check with:
        | key                    | value       |
        | stdin                  | {}          |
        | env.CLAUDE_PLUGIN_ROOT | plugin      |
        | env.CLAUDE_CONFIG_DIR  | claude-home |
      And alice runs the tool-call check with:
        | key                    | value                 |
        | stdin                  | {"tool_name": "Bash"} |
        | env.CLAUDE_PLUGIN_ROOT | plugin-copy           |
        | env.CLAUDE_CONFIG_DIR  | claude-home           |
      Then the command fails with integrity violation
      And the stderr output contains:
        """
        tools/bdd/bddlib/guard.py (enforcement file) was changed
        """

  @R-109.2
  Rule: The first prompt after setting up takes the first baseline

    @EX-109.2.1
    Scenario: The baseline a tool call found missing after setting up is taken at the first prompt
      When alice runs init with:
        | key                   | value       |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      And alice runs the tool-call check with:
        | key                   | value                 |
        | stdin                 | {"tool_name": "Bash"} |
        | env.CLAUDE_CONFIG_DIR | claude-home           |
      And alice runs the prompt check with:
        | key                   | value       |
        | stdin                 | {}          |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      And alice runs the tool-call check with:
        | key                   | value                 |
        | stdin                 | {"tool_name": "Bash"} |
        | env.CLAUDE_CONFIG_DIR | claude-home           |
      Then the command succeeds

  @R-109.3
  Rule: Only the person can acknowledge an open violation, by typing the approval command with a reason

    @EX-109.3.1
    Scenario: The person acknowledges a violation and it closes with the reason
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file acknowledging session transcript contains:
        """
        {"type":"user","promptId":"p","origin":{"kind":"human"},"message":{"content":"/greenlight:approve integrity moved"}}
        """
      When alice runs the prompt check with:
        | key                   | value       |
        | stdin                 | {}          |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      And alice runs add the standards
      And alice runs the tool-call check with:
        | key                   | value                 |
        | stdin                 | {"tool_name": "Bash"} |
        | env.CLAUDE_CONFIG_DIR | claude-home           |
      And alice runs the approval hook with:
        | key   | value                                                                                        |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve integrity moved"} |
      And alice runs the tool-call check with:
        | key                   | value                 |
        | stdin                 | {"tool_name": "Bash"} |
        | env.CLAUDE_CONFIG_DIR | claude-home           |
      Then the command succeeds
      And the output file integrity record contains:
        """
        "reason": "moved"
        """

    @EX-109.3.2
    Scenario: An acknowledgement the person did not type does not count
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file acknowledging session transcript contains:
        """
        {"type":"user","promptId":"p","origin":{"kind":"agent"},"message":{"content":"/greenlight:approve integrity moved"}}
        """
      When alice runs the tool-call check with:
        | key                   | value                 |
        | stdin                 | {"tool_name": "Bash"} |
        | env.CLAUDE_CONFIG_DIR | claude-home           |
      And alice runs the approval hook with:
        | key   | value                                                                                        |
        | stdin | {"prompt_id":"p","transcript_path":"s.jsonl","prompt":"/greenlight:approve integrity moved"} |
      And alice runs status with:
        | key                   | value       |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      Then the stdout output contains:
        """
        integrity: 1 violation(s) open
        """

    @EX-109.3.3
    Scenario: A command cannot acknowledge a violation
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs approve with:
        | key | value     |
        | arg | integrity |
        | arg | moved     |
      Then the command fails with usage error
      And the stderr output contains:
        """
        only the person can acknowledge
        """

  @R-109.4
  Rule: A change a tool call saw stays open until the person acknowledges it, and the prompt says how

    @EX-109.4.1
    Scenario: The next prompt names the one line that closes the open violations
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs the prompt check with:
        | key                   | value       |
        | stdin                 | {}          |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      And alice runs add the standards
      And alice runs the tool-call check with:
        | key                   | value                 |
        | stdin                 | {"tool_name": "Bash"} |
        | env.CLAUDE_CONFIG_DIR | claude-home           |
      And alice runs the prompt check with:
        | key                   | value       |
        | stdin                 | {}          |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      Then the stdout output contains:
        """
        type one line in Claude Code: /greenlight:approve integrity #1 <reason>
        """

    @EX-109.4.2
    Scenario: A record that claims the change came before the tool call changes nothing
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file call record contains:
        """
        {"schema": 1, "stats": {}, "calls": {"c-1": {"started": "2999-01-01T00:00:00+00:00", "alone": true}}}
        """
      When alice runs the prompt check with:
        | key                   | value       |
        | stdin                 | {}          |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      And alice runs add the standards
      And alice runs the tool-call check with:
        | key                   | value                                       |
        | stdin                 | {"tool_name": "Bash", "tool_use_id": "c-1"} |
        | env.CLAUDE_CONFIG_DIR | claude-home                                 |
      And alice runs the prompt check with:
        | key                   | value       |
        | stdin                 | {}          |
        | env.CLAUDE_CONFIG_DIR | claude-home |
      Then the stdout output contains:
        """
        an integrity violation is still open
        """
