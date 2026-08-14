"""Structural contracts for the Terraform configuration, pinned after the
2026-08-13 review.

CR-07: ``module "dns_resolver"`` must serialize after BOTH spoke peerings.
The resolver's forwarding VNet links reference spoke VNets whose hub-side
peerings Azure may not have finished provisioning when the link create is
issued — the ``ReferencedResourceNotProvisioned`` class that already bit
this repo once (PR #13 fixed the same race between the two spokes). The
expression-level references in ``forwarding_vnet_links`` order the resolver
after the spoke *VNets*, not after the *peerings*, so the ordering must be
an explicit ``depends_on`` on the whole modules.

A live proof needs a resolver-enabled session (cost-gated, issue #18); this
pin is the regression test that fails when the ``depends_on`` is absent —
written to fail when the thing it looks for is missing rather than to
quietly match something else, per the test_workflow_gates.py convention.
"""

import re
from pathlib import Path

TERRAFORM_DIR = Path(__file__).resolve().parents[2] / "terraform"
LAB_MAIN = TERRAFORM_DIR / "envs" / "lab" / "main.tf"


def _block_body(text, header_re, what):
    """The brace-balanced body of the first block whose header matches.

    Regex alone cannot bound an HCL block that contains nested braces
    (``forwarding_vnet_links = { ... }``), so walk the braces. Fails loudly
    when the header is absent — a pin that cannot find its target must not
    pass.
    """
    match = re.search(header_re, text)
    assert match, f"no {what} in {LAB_MAIN}"
    depth = 0
    start = text.index("{", match.end() - 1)
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
    raise AssertionError(f"unbalanced braces after {what} in {LAB_MAIN}")


def test_dns_resolver_depends_on_both_spoke_modules():
    body = _block_body(
        LAB_MAIN.read_text(encoding="utf-8"),
        r'module\s+"dns_resolver"\s*\{',
        'module "dns_resolver" block',
    )
    depends = re.search(r"depends_on\s*=\s*\[([^\]]*)\]", body)
    assert depends, (
        'module "dns_resolver" has no depends_on — the resolver can race the '
        "spoke peerings (ReferencedResourceNotProvisioned, cf. PR #13)"
    )
    deps = depends.group(1)
    for module in ("module.spoke_app", "module.spoke_mgmt"):
        assert re.search(rf"{re.escape(module)}\s*[,\]\s]", deps + "]"), (
            f"module \"dns_resolver\" depends_on does not include {module}"
        )


def test_every_vm_image_version_is_pinned():
    """WR-05: a floating ``version = "latest"`` lets a marketplace publish
    change what an already-reviewed plan deploys. Every source_image_reference
    must pin an explicit version; bumps arrive deliberately via PR.

    Fails when no source_image_reference exists at all — a pin with nothing
    to pin is a broken guard, not a passing one.
    """
    blocks = []
    for tf in sorted(TERRAFORM_DIR.rglob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for match in re.finditer(
            r"source_image_reference\s*\{([^}]*)\}", text, re.DOTALL
        ):
            blocks.append((tf, match.group(1)))
    assert blocks, f"no source_image_reference blocks found under {TERRAFORM_DIR}"
    for tf, body in blocks:
        version = re.search(r'version\s*=\s*"([^"]*)"', body)
        assert version, f"{tf}: source_image_reference has no version attribute"
        assert version.group(1).lower() != "latest", (
            f"{tf}: source_image_reference floats on version=latest — "
            "pin the exact marketplace version (WR-05)"
        )
