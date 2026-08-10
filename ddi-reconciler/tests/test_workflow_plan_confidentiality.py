"""NEW-CR-01 (2026-08-10 review) + PR #11 review hardening: saved-plan
confidentiality contract for workflow artifacts.

A Terraform saved plan embeds the value of every input variable (including
the HOME_IP GitHub Secret), the full prior state snapshot (hub public IP,
every NSG rule), and the backend configuration (the state storage-account
name the workflows mask out of their logs). On a public repository any
authenticated GitHub user can download workflow-run artifacts, so a raw
plan binary must never be uploaded as one.

The fixed design: plan binaries and the human-readable plan output travel
through the private ``tfplans`` container in the state storage account
(both plan and apply jobs already authenticate to it via OIDC), and the
workflow artifact carries only the sanitized manifest and summary.

This guard fails CLOSED (PR #11 review): it scans both ``*.yml`` and
``*.yaml``, and instead of blocklisting plan-binary basenames it
allowlists the exact sanitized files each workflow may upload. Directory
paths, globs, ``${{ }}`` expressions, unknown paths, and uploads from
workflows with no allowlist entry are all violations — so a rename, a
directory upload, or a brand-new workflow cannot smuggle the plan out.
"""

from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"

# The complete set of files each workflow is permitted to upload as a
# public artifact. Extending this list is a conscious, reviewed act.
ALLOWED_ARTIFACT_PATHS = {
    "plan.yml": {
        "terraform/envs/lab/plan-manifest.json",
        "terraform/envs/lab/plan-summary.txt",
    },
    "destroy.yml": {
        "terraform/envs/lab/destroy-manifest.json",
        "terraform/envs/lab/destroy-summary.txt",
    },
}

_GLOB_CHARS = frozenset("*?[]!")


def iter_upload_artifact_paths(workflows):
    """Yield (workflow, job, path-entry) for every upload-artifact path line.

    ``workflows`` is an iterable of (name, parsed-yaml) pairs so the fixture
    tests below can feed synthetic structures through the same code path the
    real scan uses.
    """
    for workflow_name, data in workflows:
        for job_name, job in ((data or {}).get("jobs") or {}).items():
            for step in job.get("steps") or []:
                uses = step.get("uses") or ""
                if not uses.startswith("actions/upload-artifact"):
                    continue
                raw_path = (step.get("with") or {}).get("path") or ""
                entries = [line.strip() for line in str(raw_path).splitlines()
                           if line.strip()]
                if not entries:
                    # An upload-artifact step with no path defaults to the
                    # whole workspace — never acceptable here.
                    yield workflow_name, job_name, "<missing path>"
                for entry in entries:
                    yield workflow_name, job_name, entry


def violations_in(workflows):
    """Every upload path that is not an exact allowlisted sanitized file."""
    found = []
    for workflow, job, entry in iter_upload_artifact_paths(workflows):
        allowed = ALLOWED_ARTIFACT_PATHS.get(workflow, set())
        problems = []
        if any(ch in _GLOB_CHARS for ch in entry):
            problems.append("glob pattern")
        if "${{" in entry:
            problems.append("expression")
        if entry.endswith(("/", "\\")) or entry in {".", "..", "<missing path>"}:
            problems.append("directory upload")
        if entry not in allowed:
            problems.append("not on the sanitized allowlist")
        if problems:
            found.append(f"{workflow}:{job} uploads {entry!r} ({', '.join(problems)})")
    return found


def repo_workflows():
    files = sorted(
        list(WORKFLOWS_DIR.glob("*.yml")) + list(WORKFLOWS_DIR.glob("*.yaml")))
    return [(f.name, yaml.safe_load(f.read_text(encoding="utf-8"))) for f in files]


def _workflow_with_upload(name, path_value):
    return [(name, {"jobs": {"j": {"steps": [
        {"uses": "actions/upload-artifact@v4", "with": {"path": path_value}}]}}})]


def test_scan_still_sees_the_artifact_upload_steps():
    # Guards the guard: if upload-artifact is renamed or the workflows are
    # restructured so the scan matches nothing, this fails instead of the
    # confidentiality test passing vacuously.
    seen = {w for w, _job, _entry in iter_upload_artifact_paths(repo_workflows())}
    assert {"plan.yml", "destroy.yml"} <= seen, (
        f"expected upload-artifact steps in plan.yml and destroy.yml, saw {sorted(seen)}"
    )


def test_every_repo_artifact_upload_is_an_allowlisted_sanitized_file():
    violations = violations_in(repo_workflows())
    assert not violations, (
        "Workflow artifacts on this public repository may contain only the "
        "sanitized manifest/summary files (NEW-CR-01); plans live in the "
        "private tfplans container: " + "; ".join(violations)
    )


# --- negative fixtures: the bypasses the PR #11 review named must all fail ---

def test_a_raw_plan_upload_is_a_violation():
    assert violations_in(_workflow_with_upload("plan.yml", "terraform/envs/lab/tfplan"))


def test_a_renamed_plan_binary_is_a_violation():
    assert violations_in(_workflow_with_upload("plan.yml", "terraform/envs/lab/plan.bin"))


def test_a_directory_upload_is_a_violation():
    assert violations_in(_workflow_with_upload("plan.yml", "terraform/envs/lab/"))
    assert violations_in(_workflow_with_upload("plan.yml", "."))


def test_a_glob_upload_is_a_violation():
    assert violations_in(_workflow_with_upload("plan.yml", "terraform/**"))
    assert violations_in(_workflow_with_upload("plan.yml", "terraform/envs/lab/tfplan*"))


def test_an_expression_upload_is_a_violation():
    assert violations_in(
        _workflow_with_upload("plan.yml", "${{ steps.plan.outputs.dir }}"))


def test_an_upload_from_a_workflow_without_an_allowlist_is_a_violation():
    # Covers future .yaml workflows too: no allowlist entry means no uploads.
    assert violations_in(_workflow_with_upload("new-pipeline.yaml", "some/file.txt"))


def test_a_missing_path_defaults_to_the_workspace_and_is_a_violation():
    assert violations_in(
        [("plan.yml", {"jobs": {"j": {"steps": [
            {"uses": "actions/upload-artifact@v4", "with": {}}]}}})])


def test_the_exact_sanitized_files_pass():
    ok = [("plan.yml", {"jobs": {"j": {"steps": [
        {"uses": "actions/upload-artifact@v4",
         "with": {"path": "terraform/envs/lab/plan-manifest.json\n"
                          "terraform/envs/lab/plan-summary.txt"}}]}}})]
    assert violations_in(ok) == []
