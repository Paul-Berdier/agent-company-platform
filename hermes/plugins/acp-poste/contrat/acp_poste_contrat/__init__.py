"""Contrat Python partagé entre le poste (apps/poste : Windows en P5, exécutant Linux en P6) et le greffon acp-poste.

- :mod:`quotas` : modèles des quotas d'abonnement (Codex CLI, Claude Code), repris tels quels de
  ``acp_contracts.subscriptions`` (étiquette archive/acp-0.10.0-avant-hermes) ; leur réduction au schéma de
  ``hermes usage --json`` est prévue en P6 (docs/refonte/plan.md) ;
- :mod:`inventaire` (étape P4, décision D21 ; étendu en P5 sans rien restreindre) : relevé d'une voie du poste
  et inventaire complet publié sur ``/machine/v1/inventaire``, garde « aucun identifiant » ;
- :mod:`machine` (étape P5, étendu en P6) : protocole ``acp-machine/1`` (requêtes et réponses des neuf routes
  machine, carte servie par ``reclamer``, formes des jetons, empreintes) ;
- :mod:`motifs_secrets` (étape P5, déplacé depuis le noyau du greffon) : motifs de secrets refusés, une seule
  copie pour le greffon, le poste et ``scripts/balayer_secrets.py``.
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
    QUOTA_SOURCES_BY_PROVIDER,
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
