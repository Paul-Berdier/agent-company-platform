"""Contrat Python partagé entre le poste Windows (apps/poste) et le greffon acp-poste.

Aujourd'hui : les modèles des quotas d'abonnement (Codex CLI, Claude Code), repris
tels quels de ``acp_contracts.subscriptions`` (étiquette archive/acp-0.10.0-avant-hermes).
Leur réduction au schéma de ``hermes usage --json`` est prévue en P6
(docs/refonte/plan.md).
"""

from .quotas import (  # noqa: F401
    DEFAULT_LIMIT_ID,
    DEFAULT_QUOTA_STALE_SECONDS,
    PROBE_LIMIT_ID,
    PROBE_STATUSES,
    QUOTA_BATCH_MAX,
    QUOTA_DETAIL_MAX,
    QUOTA_FUTURE_TOLERANCE,
    QUOTA_PLAN_MAX,
    QUOTA_SOURCE_BY_PROVIDER,
    QUOTA_SOURCES,
    QUOTA_STALE_SECONDS_MAX,
    QUOTA_STALE_SECONDS_MIN,
    QUOTA_WINDOWS_MAX,
    SUBSCRIPTION_PROVIDERS,
    ProbeStatus,
    QuotaCredits,
    QuotaSource,
    QuotaWindow,
    QuotaWindowView,
    SubscriptionProvider,
    SubscriptionQuotaBatch,
    SubscriptionQuotaIngestResult,
    SubscriptionQuotaList,
    SubscriptionQuotaReport,
    SubscriptionQuotaView,
)
