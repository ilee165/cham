"""NEW-CR-01 (2026-08-10 review): saved-plan confidentiality contract.

A Terraform saved plan embeds the value of every input variable (including
the HOME_IP GitHub Secret), the full prior state snapshot (hub public IP,
every NSG rule), and the backend configuration (the state storage-account
name the workflows mask out of their logs). On a public repository any
authenticated GitHub user can download workflow-run artifacts, so a raw
plan binary must never be uploaded as one.

The fixed design: plan binaries travel through the private ``tfplans``
container in the state storage account (both plan and apply jobs already
authenticate to it via OIDC), and the workflow artifact carries only the
sanitized manifest and summary. This test parses every workflow and fails
closed if any ``actions/upload-artifact`` step reintroduces a ``tfplan`` /
``*.tfplan`` path.
"""

from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def iter_upload_artifact_paths():
    """Yield (workflow, job, path-entry) for every upload-artifact path line."""
    for workflow in sorted(WORKFLOWS_DIR.glob("*.yml")):
        data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        for job_name, job in (data.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                uses = step.get("uses") or ""
                if not uses.startswith("actions/upload-artifact"):
                    continue
                raw_path = (step.get("with") or {}).get("path") or ""
                for line in str(raw_path).splitlines():
                    entry = line.strip()
                    if entry:
                        yield workflow.name, job_name, entry


def _is_plan_binary(entry: str) -> bool:
    basename = entry.replace("\\", "/").rsplit("/", 1)[-1]
    return basename == "tfplan" or basename.endswith(".tfplan")


def test_scan_still_sees_the_artifact_upload_steps():
    # Guards the guard: if upload-artifact is renamed or the workflows are
    # restructured so the scan matches nothing, this fails instead of the
    # confidentiality test passing vacuously.
    seen = {workflow for workflow, _job, _entry in iter_upload_artifact_paths()}
    assert {"plan.yml", "destroy.yml"} <= seen, (
        f"expected upload-artifact steps in plan.yml and destroy.yml, saw {sorted(seen)}"
    )


def test_no_raw_saved_plan_is_uploaded_as_a_workflow_artifact():
    violations = [
        f"{workflow}:{job} uploads {entry!r}"
        for workflow, job, entry in iter_upload_artifact_paths()
        if _is_plan_binary(entry)
    ]
    assert not violations, (
        "Raw saved plans must go to the private tfplans container, never into "
        "a workflow artifact on this public repository (NEW-CR-01): "
        + "; ".join(violations)
    )
