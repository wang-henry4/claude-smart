"""Ground-truth scenarios for the claude-mem vs claude-smart benchmark.

Each scenario scripts a short multi-turn Claude CLI conversation. Both plugins
observe the session via their hooks and independently extract memory. After
the session, ``probe_query`` is fired at each system and the retrieved text
is scored against ``ground_truth`` by an LLM judge.

Categories:
    - personalization: durable user preferences ("I always use X")
    - correction: user pushes back on the assistant's approach
    - general: role, team, or project context that should persist
    - learning: probes that ask for a *rule to apply going forward*, not
      "what happened before". Exposes whether a system produces behavioral
      rules (claude-smart) or only descriptive history (claude-mem). Both
      systems see identical source turns; the probe is the differentiator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    """A single benchmark case.

    Attributes:
        id (str): Stable slug, used for scratch dir + result keying.
        category (str): One of ``personalization``, ``correction``, ``general``.
        turns (tuple[str, ...]): User messages delivered in order; each turn
            is one Claude session (first via ``-p``, rest via ``--resume``).
        ground_truth (str): The fact we expect both systems to capture.
        probe_query (str): Retrieval query fired at each system post-session.
    """

    id: str
    category: str
    turns: tuple[str, ...]
    ground_truth: str
    probe_query: str


SCENARIOS: tuple[Scenario, ...] = (
    # --- personalization ---
    Scenario(
        id="pref-testfmk",
        category="personalization",
        turns=(
            "I'm starting a new Python project. Give me a one-line summary "
            "of what test framework you'd suggest.",
            "I always use pytest, never unittest — make that a project-wide "
            "rule for me going forward.",
            "Good. Write a one-line sample test for a function add(a, b).",
        ),
        ground_truth="User prefers pytest over unittest as a project-wide rule.",
        probe_query="What Python test framework does the user prefer?",
    ),
    Scenario(
        id="pref-formatting",
        category="personalization",
        turns=(
            "What indent style is most common in Python?",
            "For my code, always use 4-space indents and double quotes — "
            "don't ever suggest tabs or single quotes.",
            "Show a one-line example of a dict literal in my preferred style.",
        ),
        ground_truth=(
            "User requires 4-space indents and double quotes in Python code; "
            "no tabs, no single quotes."
        ),
        probe_query="What formatting style does the user require for Python code?",
    ),
    Scenario(
        id="pref-stack",
        category="personalization",
        turns=(
            "I'm picking a deployment target for a small API.",
            "I deploy everything on Railway and always use Postgres over "
            "MySQL — remember that for all my projects.",
            "Given that, suggest a one-line DATABASE_URL env var format.",
        ),
        ground_truth=(
            "User deploys on Railway and prefers Postgres over MySQL "
            "across all projects."
        ),
        probe_query="Where does the user deploy and what database do they prefer?",
    ),
    # --- correction ---
    Scenario(
        id="corr-async",
        category="correction",
        turns=(
            "Write a one-line Python function fetch_user(id) that calls an "
            "HTTP API using httpx.",
            "Stop using async — this codebase is fully synchronous. "
            "Never write async code in this project.",
            "Rewrite the function synchronously in one line.",
        ),
        ground_truth=(
            "User corrected: this codebase is synchronous; do not write async "
            "code in this project."
        ),
        probe_query="Should async code be used in this project?",
    ),
    Scenario(
        id="corr-verbose",
        category="correction",
        turns=(
            "Write a one-line function square(x) with a full docstring.",
            "No, stop writing docstrings and comments — I want terse code "
            "only. Keep it minimal from now on.",
            "Rewrite square(x) in your new style, one line.",
        ),
        ground_truth=(
            "User corrected: no docstrings or comments; keep code terse and minimal."
        ),
        probe_query="Does the user want docstrings and comments in their code?",
    ),
    Scenario(
        id="corr-lib",
        category="correction",
        turns=(
            "Give me a one-line snippet to parse a YAML file in Python.",
            "No, don't use PyYAML — it's insecure. We only use ruamel.yaml "
            "in this project. Stick to that.",
            "Redo it in one line with the right library.",
        ),
        ground_truth=(
            "User corrected: do not use PyYAML due to security; use "
            "ruamel.yaml in this project."
        ),
        probe_query="What YAML library should be used in this project, and what should be avoided?",
    ),
    # --- general ---
    Scenario(
        id="gen-role",
        category="general",
        turns=(
            "Hi, I want to ask about observability tooling.",
            "Context for you: I'm a data scientist, and I'm currently "
            "investigating what logging and tracing we have in our ETL "
            "pipelines.",
            "Given that context, name one tool I should look into. One line.",
        ),
        ground_truth=(
            "User is a data scientist currently working on observability "
            "and logging for ETL pipelines."
        ),
        probe_query="What is the user's role and current focus?",
    ),
    Scenario(
        id="gen-team",
        category="general",
        turns=(
            "Quick planning question about releases.",
            "Context: I maintain the billing service. My team is 3 people "
            "and we ship every Friday. Remember that.",
            "Given that cadence, when should I cut a release branch for a "
            "change merging Wednesday? One line.",
        ),
        ground_truth=(
            "User maintains the billing service on a 3-person team with "
            "weekly Friday releases."
        ),
        probe_query="What service does the user own and what is their release cadence?",
    ),
    Scenario(
        id="gen-freeze",
        category="general",
        turns=(
            "I'm prioritizing merges this week.",
            "Heads up — we're freezing all non-critical merges after "
            "Thursday because the mobile team is cutting a release branch. "
            "Keep that in mind for any PR work.",
            "Given that, should a nice-to-have refactor PR ship today or wait? One line.",
        ),
        ground_truth=(
            "Merge freeze for non-critical PRs starts after Thursday due to "
            "the mobile release-branch cut."
        ),
        probe_query="Is there a merge freeze coming up, and why?",
    ),
    # --- learning vs memory highlight scenarios ---
    # Each of these: the user reports a past event. The probe asks for a
    # FUTURE-FACING RULE. A memory system (descriptive) can surface the
    # event but not the rule; a learning system (prescriptive) produces
    # the rule directly. Ground truth is written as the rule, not the event.
    Scenario(
        id="learn-api-v2",
        category="learning",
        turns=(
            "Quick note on our internal-api client.",
            "We migrated every call in the codebase from internal-api v1 to "
            "v2 last sprint. v1 is going away — any new code should target "
            "v2 going forward.",
            "Got it. Paste me a one-line import for the v2 client.",
        ),
        ground_truth=(
            "Behavioral rule: new code must use internal-api v2; do not "
            "suggest or write v1 calls."
        ),
        probe_query=(
            "When I add a new internal-api call in this project, which "
            "version should I use, and is there a version I should avoid?"
        ),
    ),
    Scenario(
        id="learn-naming",
        category="learning",
        turns=(
            "Style question for this project.",
            "We just refactored every identifier in the repo from snake_case "
            "(usr_id, fetch_data) to camelCase (userId, fetchData). That's "
            "now the house convention for all new TS code.",
            "Acknowledged. Give me a one-line type alias for a user-id field "
            "in your preferred style.",
        ),
        ground_truth=(
            "Behavioral rule: all new TS identifiers in this project use "
            "camelCase; do not write snake_case identifiers."
        ),
        probe_query=(
            "What naming convention should I use for new identifiers in this "
            "project's TypeScript code?"
        ),
    ),
    Scenario(
        id="learn-pagination",
        category="learning",
        turns=(
            "I want to flag a bug class to watch out for.",
            "We just fixed an off-by-one in our pagination helper — the "
            "`offset + limit` calculation was computing the LAST index "
            "instead of the COUNT. Same bug shape has now bitten us three "
            "times in different files. Treat pagination boundary math as a "
            "high-risk area going forward.",
            "Understood. Write a one-line assertion I could add in review.",
        ),
        ground_truth=(
            "Behavioral rule: treat pagination offset/limit boundary math "
            "as high-risk; verify offset-vs-count semantics and add "
            "boundary-value tests."
        ),
        probe_query=(
            "What should I double-check or test whenever I touch pagination "
            "code in this project?"
        ),
    ),
)
