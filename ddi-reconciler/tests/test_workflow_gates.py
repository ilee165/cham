"""Structural contracts for the CI gates, pinned after the 2026-08-11 review.

Two properties this repository depends on cannot be expressed in the
reconciler's own code, because they live in workflow YAML:

1. **The public edge cannot be suppressed.** ``dwsolution.co`` is a live
   production zone carrying Microsoft 365 mail records. Its nightly drift
   check must not be able to fail for a reason originating in Azure — which
   is exactly what happened when both edges shared one ``cham-reconcile``
   invocation, since the CLI iterates edges in config order with no per-edge
   error isolation.

2. **An environment-gated job runs only the reviewed workflow file.**
   ``workflow_dispatch`` executes the workflow from whatever ref was
   dispatched, and every verification step lives inside that same file, so a
   job holding production credentials must pin ``github.ref`` rather than
   leaning entirely on the environment's branch policy.

Both are invisible in a diff and easy to undo by "simplifying" the workflow,
so they are asserted here.
"""

from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name):
    return yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"))


def _steps(workflow, job_name):
    return _load(workflow)["jobs"][job_name].get("steps") or []


def _step_text(step):
    # `with.script` matters too: github-script steps carry their whole body
    # there, so a scan that reads only `run` would miss the issue-filing logic.
    script = (step.get("with") or {}).get("script", "")
    return f"{step.get('uses', '')}\n{step.get('run', '')}\n{script}"


def _index_of(steps, predicate):
    for i, step in enumerate(steps):
        if predicate(step):
            return i
    return -1


# --- drift: the public edge runs first, credential-free, and gates ---

def _drift_steps():
    return _steps("drift.yml", "drift")


def test_public_edge_is_checked_before_any_azure_login():
    steps = _drift_steps()
    public = _index_of(steps, lambda s: "--edge cloudflare-public" in _step_text(s))
    login = _index_of(steps, lambda s: "azure/login" in (s.get("uses") or ""))
    assert public >= 0, "no step runs the reconciler against cloudflare-public"
    assert login >= 0, "no azure/login step found"
    assert public < login, (
        "the public-edge check must run before Azure login, so that a rotated "
        "credential or an Entra outage cannot stop the production zone from "
        "being checked"
    )


def test_the_two_edges_are_separate_invocations():
    steps = _drift_steps()
    both = [s for s in steps
            if "--edge cloudflare-public" in _step_text(s)
            and "--edge azure-private" in _step_text(s)]
    assert not both, (
        "one invocation covering both edges lets an Azure error abort the run "
        "before the public edge is fetched — cham-reconcile iterates edges in "
        "config order and has no per-edge error isolation"
    )


def test_the_public_edge_check_is_not_best_effort():
    steps = _drift_steps()
    public = steps[_index_of(steps, lambda s: "--edge cloudflare-public" in _step_text(s))]
    assert not public.get("continue-on-error"), (
        "the public-edge step carries the exit-code gate; marking it "
        "continue-on-error would make a broken reconciler look like a "
        "converged night"
    )


def test_every_azure_step_is_best_effort():
    steps = _drift_steps()
    login = _index_of(steps, lambda s: "azure/login" in (s.get("uses") or ""))
    azure_steps = [s for s in steps[login:]
                   if "azure/login" in (s.get("uses") or "")
                   or "az " in _step_text(s)
                   or "--edge azure-private" in _step_text(s)]
    assert azure_steps, "expected azure login, presence probe and edge check"
    offenders = [s.get("name", "<unnamed>") for s in azure_steps
                 if not s.get("continue-on-error")]
    assert not offenders, (
        "these Azure steps would abort the job and take the public drift "
        f"report with them: {offenders}"
    )


def test_an_azure_failure_still_fails_the_run():
    steps = _drift_steps()
    final = [s for s in steps if str(s.get("if", "")).strip().startswith("always()")
             and "azure" in _step_text(s).lower()]
    assert final, (
        "azure steps are continue-on-error, so something must run "
        "unconditionally at the end and turn an unchecked azure edge red — "
        "otherwise the failure is silent"
    )


def test_the_drift_report_does_not_open_duplicate_issues():
    steps = _drift_steps()
    report = [s for s in steps if "issues.create" in _step_text(s)]
    assert report, "no step files a drift issue"
    text = _step_text(report[0])
    assert "listForRepo" in text and "createComment" in text, (
        "a rebuilt lab legitimately reports drift every night; without a "
        "lookup for the open drift issue the repository fills with duplicates"
    )


# --- apply/destroy: credentialed jobs are pinned to main ---

GATED_JOBS = [
    ("apply.yml", "apply"),
    ("apply.yml", "apply-cloudflare"),
    ("destroy.yml", "apply-destroy"),
]


def test_every_environment_gated_job_is_pinned_to_main():
    for workflow, job_name in GATED_JOBS:
        job = _load(workflow)["jobs"][job_name]
        assert job.get("environment"), f"{workflow}:{job_name} lost its environment gate"
        condition = " ".join(str(job.get("if", "")).split())
        assert "github.ref == 'refs/heads/main'" in condition, (
            f"{workflow}:{job_name} does not pin github.ref. Dispatch runs the "
            "workflow file from the dispatched ref, and every verification "
            "step in the job lives inside that file"
        )


def test_the_cloudflare_apply_does_not_share_an_environment_with_teardown():
    cloudflare = _load("apply.yml")["jobs"]["apply-cloudflare"]["environment"]
    others = {_load("apply.yml")["jobs"]["apply"]["environment"],
              _load("destroy.yml")["jobs"]["apply-destroy"]["environment"]}
    assert cloudflare not in others, (
        "environment secrets are scoped to the environment, never to a job: "
        "sharing one would put the live-zone DNS:Edit token inside the secret "
        "scope of every lab apply and teardown, so approving a routine "
        "destroy would grant it"
    )


def test_every_environment_gated_job_asserts_its_branch_policy():
    for workflow, job_name in GATED_JOBS:
        text = "\n".join(_step_text(s) for s in _steps(workflow, job_name))
        assert "required_reviewers" in text, (
            f"{workflow}:{job_name} no longer asserts a required-reviewer rule")
        assert "deployment-branch-policies" in text or "protected_branches" in text, (
            f"{workflow}:{job_name} asserts reviewers but not the branch "
            "policy — the unasserted control is the one nobody notices losing")
