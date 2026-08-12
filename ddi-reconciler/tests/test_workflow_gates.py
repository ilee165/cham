"""Structural contracts for the CI gates, pinned after the 2026-08-11 reviews.

Two properties this repository depends on cannot be expressed in the
reconciler's own code, because they live in workflow YAML:

1. **The public edge cannot be suppressed.** ``dwsolution.co`` is a live
   production zone carrying Microsoft 365 mail records. Its nightly drift
   check must not be able to fail for a reason originating in Azure.

2. **An environment-gated job runs only the reviewed workflow file.**
   ``workflow_dispatch`` executes the workflow from whatever ref was
   dispatched, and every verification step lives inside that same file, so a
   job holding production credentials must pin ``github.ref`` rather than
   leaning entirely on the environment's branch policy.

The first draft of this module asserted both properties too loosely, and a
review demonstrated the gap by mutation: deleting the step that turns an
Azure failure red, or adding a whole unpinned environment-gated apply job,
left the suite green. Every helper below is therefore written to fail when
the thing it looks for is absent rather than to quietly match something
else — a guard that cannot fail is worse than no guard, because it is
mistaken for one.
"""

import re
from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"

# Steps that talk to Azure, identified by step id rather than by scanning
# prose for "az ". The substring form pulled in any step whose comment
# happened to contain those two characters — including the final gate, whose
# entire purpose is to fail the run — and would then demand it be made
# best-effort.
AZURE_STEP_IDS = frozenset({"login", "zone", "azure"})


def _load(name):
    return yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"))


def _workflow_files():
    return sorted(list(WORKFLOWS_DIR.glob("*.yml")) + list(WORKFLOWS_DIR.glob("*.yaml")))


def _steps(workflow, job_name):
    return _load(workflow)["jobs"][job_name].get("steps") or []


def _step_text(step):
    # `with.script` matters too: github-script steps carry their whole body
    # there, so a scan reading only `run` would miss the issue-filing logic.
    script = (step.get("with") or {}).get("script", "")
    return f"{step.get('uses', '')}\n{step.get('run', '')}\n{script}"


def _step_code(step):
    """`_step_text` with comment lines removed.

    An assertion that a workflow does not *use* something must not trip over
    a comment explaining why it does not use it.
    """
    return "\n".join(
        line for line in _step_text(step).splitlines()
        if not line.strip().startswith(("#", "//")))


def _only_step(steps, predicate, what):
    """The single step matching `predicate`, or a failure naming what was sought.

    Never returns an index: the earlier draft passed `_index_of`'s -1 straight
    into `steps[...]`, which is the LAST step in Python, so removing the
    public-edge check made the test silently assert against the final gate and
    pass.
    """
    matches = [s for s in steps if predicate(s)]
    assert matches, f"no step in this job {what}"
    return matches[0]


def _position(steps, predicate, what):
    for i, step in enumerate(steps):
        if predicate(step):
            return i
    raise AssertionError(f"no step in this job {what}")


def environment_gated_jobs():
    """Every job in every workflow that declares an `environment:`.

    Derived, never enumerated. A hardcoded list made the three "every
    environment-gated job ..." tests below blind to exactly the regression
    they exist to catch: a new credentialed job someone forgot to add.
    """
    found = []
    for path in _workflow_files():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in (data.get("jobs") or {}).items():
            environment = job.get("environment")
            if not environment:
                continue
            name = environment if isinstance(environment, str) else environment.get("name")
            found.append((path.name, job_name, name))
    return found


def test_the_derivation_actually_finds_the_gated_jobs():
    # Guards the guard: if `environment:` is restructured so the scan matches
    # nothing, the universal tests below would pass vacuously over an empty
    # list. Fail here instead.
    jobs = environment_gated_jobs()
    assert len(jobs) >= 3, f"expected the apply/destroy gated jobs, found {jobs}"
    assert {"apply.yml", "destroy.yml"} <= {w for w, _job, _env in jobs}


# --- drift: the public edge runs first, credential-free, and gates ---

def _drift_steps():
    return _steps("drift.yml", "drift")


def _is_public_edge_step(step):
    return "--edge cloudflare-public" in _step_text(step)


def test_public_edge_is_checked_before_any_azure_login():
    steps = _drift_steps()
    public = _position(steps, _is_public_edge_step, "checks the cloudflare-public edge")
    login = _position(steps, lambda s: "azure/login" in (s.get("uses") or ""),
                      "logs in to Azure")
    assert public < login, (
        "the public-edge check must run before Azure login, so that a rotated "
        "credential or an Entra outage cannot stop the production zone from "
        "being checked"
    )


def test_the_two_edges_are_separate_invocations():
    both = [s for s in _drift_steps()
            if "--edge cloudflare-public" in _step_text(s)
            and "--edge azure-private" in _step_text(s)]
    assert not both, (
        "one invocation covering both edges lets an Azure error abort the run "
        "before the public edge is fetched — cham-reconcile iterates edges in "
        "config order"
    )


def test_the_public_edge_check_is_not_best_effort():
    public = _only_step(_drift_steps(), _is_public_edge_step,
                        "checks the cloudflare-public edge")
    assert not public.get("continue-on-error"), (
        "the public-edge step carries the exit-code gate; marking it "
        "continue-on-error would make a broken reconciler look like a "
        "converged night"
    )


def test_every_azure_step_is_best_effort():
    azure_steps = [s for s in _drift_steps() if s.get("id") in AZURE_STEP_IDS]
    assert len(azure_steps) == len(AZURE_STEP_IDS), (
        f"expected steps with ids {sorted(AZURE_STEP_IDS)}, found "
        f"{[s.get('id') for s in azure_steps]}")
    offenders = [s.get("name", "<unnamed>") for s in azure_steps
                 if not s.get("continue-on-error")]
    assert not offenders, (
        "these Azure steps would abort the job and take the public drift "
        f"report with them: {offenders}"
    )


def _is_final_azure_gate(step):
    """The step that converts an unchecked azure edge into a red run.

    Identified by what it reads — the outcomes of the azure steps — not by the
    word "azure" appearing somewhere in it. The loose form was satisfied by
    the drift-report step, so deleting this gate entirely left the suite
    green.
    """
    text = _step_text(step) + str(step.get("env", ""))
    return (str(step.get("if", "")).strip().startswith("always()")
            and all(f"steps.{step_id}.outcome" in text for step_id in AZURE_STEP_IDS))


def test_an_azure_failure_still_fails_the_run():
    gate = _only_step(_drift_steps(), _is_final_azure_gate,
                      "reads every azure step's outcome under always()")
    text = _step_text(gate)
    assert "exit 1" in text, (
        "the gate reads the azure outcomes but never fails the run, so an "
        "unchecked azure edge would be silent")
    assert "issues." not in text, (
        "the gate must be its own step; folding it into the issue-filing step "
        "makes it conditional on drift having been found")


def test_the_gate_also_catches_a_skipped_azure_edge():
    gate = _only_step(_drift_steps(), _is_final_azure_gate,
                      "reads every azure step's outcome under always()")
    assert "skipped" in _step_text(gate), (
        "a failure in the public step skips every unconditioned step after "
        "it, so the azure outcomes read 'skipped', not 'failure' — checking "
        "only for 'failure' lets an unchecked azure edge pass unmentioned"
    )


def _files_new_issues(step):
    # `in "issues.create"` also matches `issues.createComment`, so a refactor
    # dropping the create branch left this looking satisfied.
    return re.search(r"issues\.create\s*\(", _step_text(step)) is not None


def test_the_drift_report_can_both_open_and_update_an_issue():
    report = _only_step(_drift_steps(), _files_new_issues, "opens a drift issue")
    text = _step_text(report)
    assert re.search(r"issues\.createComment\s*\(", text), (
        "a rebuilt lab legitimately reports drift every night; without a "
        "comment path the repository fills with duplicate issues")
    assert "listForRepo" in text, "nothing looks for an already-open drift issue"


def test_the_drift_report_ignores_pull_requests():
    report = _only_step(_drift_steps(), _files_new_issues, "opens a drift issue")
    assert "pull_request" in _step_text(report), (
        "issues.listForRepo returns open pull requests too, so a "
        "drift-labelled PR would silently absorb every future drift report "
        "as a comment and no issue would ever be filed"
    )


# --- apply/destroy: credentialed jobs are pinned to main ---

def test_every_environment_gated_job_is_pinned_to_main():
    for workflow, job_name, _environment in environment_gated_jobs():
        condition = " ".join(str(_load(workflow)["jobs"][job_name].get("if", "")).split())
        assert "github.ref == 'refs/heads/main'" in condition, (
            f"{workflow}:{job_name} does not pin github.ref. Dispatch runs the "
            "workflow file from the dispatched ref, and every verification "
            "step in the job lives inside that file"
        )


def test_the_cloudflare_apply_does_not_share_an_environment_with_teardown():
    by_job = {(w, j): env for w, j, env in environment_gated_jobs()}
    cloudflare = by_job[("apply.yml", "apply-cloudflare")]
    others = {env for (w, j), env in by_job.items() if (w, j) != ("apply.yml", "apply-cloudflare")}
    assert cloudflare not in others, (
        "environment secrets are scoped to the environment, never to a job: "
        "sharing one would put the live-zone DNS:Edit token inside the secret "
        "scope of every lab apply and teardown, so approving a routine "
        "destroy would grant it"
    )


def test_every_environment_gated_job_asserts_its_branch_policy():
    for workflow, job_name, _environment in environment_gated_jobs():
        text = "\n".join(_step_code(s) for s in _steps(workflow, job_name))
        assert "required_reviewers" in text, (
            f"{workflow}:{job_name} no longer asserts a required-reviewer rule")
        assert "deployment-branch-policies" in text, (
            f"{workflow}:{job_name} asserts reviewers but not the branch "
            "policy — the unasserted control is the one nobody notices losing")
        assert "protected_branches" not in text, (
            f"{workflow}:{job_name} accepts GitHub's `protected_branches` "
            "setting as proof of a main-only policy. That setting means 'any "
            "branch a protection rule or ruleset covers', so a ruleset "
            "targeting release/* would silently widen who can deploy"
        )
