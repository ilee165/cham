"""
Azure provider for cham-reconcile.

Usage:
    Uses azure-mgmt-privatedns with DefaultAzureCredential (az login locally)

CRITICAL:
    Skip records where is_auto_registered is true. Those belong to Azure's VM auto-registration.

TODO(phase 4):
    fetch_actual(), apply(diff)
"""
from
