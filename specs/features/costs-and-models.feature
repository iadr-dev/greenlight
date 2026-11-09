@FEAT-114
Feature: What the agents cost and which model they run on is on record
  The person sees what each feature cost, with figures read from the agents' own transcripts, also when several
  features are in progress. A wrong figure is corrected with a reason, and the original stays on record. Claude Code's
  own count of the orchestrator session is shown next to the record and kept out of it. The person chooses the model
  of each agent in the project's config, and the status shows which model each agent runs on.

  @R-114.1
  Rule: An agent's cost goes to the feature its task names, also when several features are in progress

    @EX-114.1.1
    Scenario: Two features in progress and an agent whose task names the second
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file first feature state contains:
        """
        {"schema": 1, "feature": "FEAT-001", "kind": "feature", "title": "Sign in", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "test-design", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "approvals": [],
         "assumptions": [], "cost": {}, "red": null, "hooks_seen": false, "changes": []}
        """
      And the input file second feature state contains:
        """
        {"schema": 1, "feature": "FEAT-002", "kind": "feature", "title": "Sign up", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "discover", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "approvals": [],
         "assumptions": [], "cost": {}, "red": null, "hooks_seen": false, "changes": []}
        """
      And the input file agent transcript contains:
        """
        {"type": "user", "timestamp": "2026-11-08T10:01:00.000Z", "message": {"role": "user", "content": "FEAT-002 discover: run the discover playbook"}}
        {"type": "assistant", "timestamp": "2026-11-08T10:01:30.000Z", "message": {"id": "msg_1", "role": "assistant", "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0}, "content": []}}
        """
      When alice runs subagent stop with:
        | key                            | value                                                                      |
        | stdin                          | {"session_id":"s","agent_id":"x","agent_type":"greenlight:product-analyst"} |
        | env.GREENLIGHT_TRANSCRIPT_ROOT | transcripts                                                                |
        | env.CLAUDE_CONFIG_DIR          | claude                                                                     |
      And alice runs cost with:
        | key                            | value       |
        | arg                            | FEAT-002    |
        | arg                            | --collect   |
        | env.GREENLIGHT_TRANSCRIPT_ROOT | transcripts |
        | env.CLAUDE_CONFIG_DIR          | claude      |
      Then the command succeeds
      And the stdout output contains:
        """
        x (greenlight:product-analyst) discover: 120 tokens, 30 s
        """

  @R-114.2
  Rule: A recorded cost is corrected with a reason, and the original stays on record

    @EX-114.2.1
    Scenario: Correcting a figure that was typed wrong
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file first feature state contains:
        """
        {"schema": 1, "feature": "FEAT-001", "kind": "feature", "title": "Sign in", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "examples", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "approvals": [],
         "assumptions": [], "cost": {"test-design": {"tokens": 150000, "seconds": 12.0, "runs": 2}}, "red": null,
         "hooks_seen": false, "changes": []}
        """
      When alice runs cost with:
        | key | value                                                       |
        | arg | FEAT-001                                                    |
        | arg | --amend                                                     |
        | arg | test-design                                                 |
        | arg | --tokens                                                    |
        | arg | 30000                                                       |
        | arg | --reason                                                    |
        | arg | 120000 tokens were typed by hand; the transcripts say 30000 |
      Then the command succeeds
      And the stdout output contains:
        """
        FEAT-001 test-design: 150,000 tokens, 12.0 s corrected to 30,000 tokens, 12.0 s
        """
      And the output file first feature state contains:
        """
        "reason": "120000 tokens were typed by hand; the transcripts say 30000"
        """
      And the output file first feature state contains:
        """
        "tokens": 150000
        """

    @EX-114.2.2
    Scenario: The report shows the correction and the figure it replaced
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file first feature state contains:
        """
        {"schema": 1, "feature": "FEAT-001", "kind": "feature", "title": "Sign in", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "examples", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "approvals": [],
         "assumptions": [], "cost": {"test-design": {"tokens": 150000, "seconds": 12.0, "runs": 2}}, "red": null,
         "hooks_seen": false, "changes": []}
        """
      When alice runs cost with:
        | key | value                         |
        | arg | FEAT-001                      |
        | arg | --amend                       |
        | arg | test-design                   |
        | arg | --tokens                      |
        | arg | 30000                         |
        | arg | --reason                      |
        | arg | typed by hand, not measured   |
      And alice runs report with:
        | key | value    |
        | arg | FEAT-001 |
      Then the command succeeds
      And the stdout output contains:
        """
        corrected from 150,000 tokens, 12.0 s: typed by hand, not measured
        """

    @EX-114.2.3
    Scenario: A correction without a reason is refused
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file first feature state contains:
        """
        {"schema": 1, "feature": "FEAT-001", "kind": "feature", "title": "Sign in", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "examples", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "approvals": [],
         "assumptions": [], "cost": {"test-design": {"tokens": 150000, "seconds": 12.0, "runs": 2}}, "red": null,
         "hooks_seen": false, "changes": []}
        """
      When alice runs cost with:
        | key | value       |
        | arg | FEAT-001    |
        | arg | --amend     |
        | arg | test-design |
        | arg | --tokens    |
        | arg | 30000       |
      Then the command fails with usage error
      And the stderr output contains:
        """
        a correction needs --reason
        """

  @R-114.3
  Rule: Claude Code's own count of the orchestrator session is shown next to the record, never added to it

    @EX-114.3.1
    Scenario: The report shows the session that started the feature's agents
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      And the input file first feature state contains:
        """
        {"schema": 1, "feature": "FEAT-001", "kind": "feature", "title": "Sign in", "created_at": "2026-11-08T10:00:00+00:00",
         "phase": "examples", "autonomy": {"level": "standard", "switches": []}, "gates": {}, "approvals": [],
         "assumptions": [], "cost": {"test-design": {"tokens": 120, "seconds": 30.0, "runs": 1}}, "cost_agents": ["a1"],
         "red": null, "hooks_seen": false, "changes": []}
        """
      And the input file agent notes contains:
        """
        {"agent_id": "a1", "session": "s", "agent": "greenlight:qa-designer", "feature": "FEAT-001", "phase": "test-design", "duration_ms": 0, "at": "2026-11-08T10:02:00+00:00"}
        """
      And the input file session transcript contains:
        """
        {"type": "assistant", "timestamp": "2026-11-08T10:00:30.000Z", "message": {"id": "msg_main_1", "role": "assistant", "usage": {"input_tokens": 5000, "output_tokens": 300, "cache_creation_input_tokens": 4000}, "content": []}}
        """
      When alice runs report with:
        | key                             | value       |
        | arg                             | FEAT-001    |
        | env.GREENLIGHT_TRANSCRIPT_ROOT  | transcripts |
        | env.CLAUDE_CONFIG_DIR           | claude      |
      Then the command succeeds
      And the stdout output contains:
        """
        Orchestrator session: 9,300 tokens
        """
      And the stdout output contains:
        """
        not part of the recorded cost
        """

  @R-114.4
  Rule: The person names a model per agent, and the status shows the model each agent runs on

    @EX-114.4.1
    Scenario: Without a choice every agent runs on the model of its agent file
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs status
      Then the command succeeds
      And the stdout output contains:
        """
        models: product-analyst opus, qa-designer opus, system-analyst opus, step-engineer sonnet, implementer sonnet, ui-engineer sonnet, code-reviewer opus, security-reviewer opus, ui-reviewer opus, spec-auditor opus
        """

    @EX-114.4.2
    Scenario: A model chosen in the project's config is shown as chosen there
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"

        [models]
        implementer = "opus"
        """
      When alice runs status
      Then the command succeeds
      And the stdout output contains:
        """
        implementer opus (.bdd/config.toml)
        """

    @EX-114.4.3
    Scenario: A model the Agent tool does not accept is reported by the doctor
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"

        [models]
        implementer = "gpt-5"
        """
      When alice runs doctor
      Then the stdout output contains:
        """
        implementer = "gpt-5" is not a model the Agent tool accepts
        """

  @R-114.5
  Rule: A spec agent edits only the files its role writes

    @EX-114.5.1 @existing
    Scenario: The QA designer may not edit production code
      Given the input file project config contains:
        """
        [[adapters]]
        name = "x"
        features = "features"
        steps = "steps"
        """
      When alice runs guard with:
        | key   | value                                                                                              |
        | stdin | {"tool_name":"Edit","agent_type":"greenlight:qa-designer","tool_input":{"file_path":"src/app.py"}} |
      Then the command fails with refused
      And the stderr output contains:
        """
        the qa-designer agent may not write production files
        """
