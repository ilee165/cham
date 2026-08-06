"""Azure Private DNS adapter — reconciled edge for azure.dwsolution.co.

CRITICAL SAFETY: record sets with is_auto_registered=True belong to Azure VM
auto-registration and are dropped at fetch time — combined with the
managed-key allowlist in diff_records they can never be updated or deleted.

Auth: DefaultAzureCredential (az login locally; OIDC-federated in CI).
"""
from ddi_reconciler.model import CanonicalRecord, Diff


class AzureProvider:
    def __init__(self, subscription_id: str, resource_group: str, client=None):
        self.resource_group = resource_group
        self._client = client  # real client construction lands in Task B6

    def fetch_actual(self, zones: set[str]) -> list[CanonicalRecord]:
        raise NotImplementedError("Task B6")

    def apply(self, diff: Diff) -> None:
        raise NotImplementedError("Task B6")
