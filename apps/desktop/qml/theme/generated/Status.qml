// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/semantic-status.json (version 2.0.0)
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root

    // Thème actif. Écrit par ThemeBridge (Acp.Theme) d'après la préférence lue par la
    // couche C++ (SystemAppearance) ; jamais deviné par un composant.
    property string theme: "atelier-nuit"
    readonly property var themes: ["atelier-nuit", "atelier-jour", "studio-graphite", "studio-papier"]
    // Faux si `theme` n'est pas un thème généré : le thème par défaut s'applique alors.
    readonly property bool known: root.themes.indexOf(root.theme) >= 0
    readonly property QtObject current: root.theme === "atelier-jour" ? root.atelierJour : root.theme === "studio-graphite" ? root.studioGraphite : root.theme === "studio-papier" ? root.studioPapier : root.atelierNuit
    readonly property bool isDark: root.current.isDark
    readonly property string family: root.current.family

    readonly property QtObject atelierNuit: QtObject {
        readonly property bool isDark: true
        readonly property string family: "atelier"
        readonly property color statusUnknownForeground: "#9ea3b8"
        readonly property color statusUnknownTint: "#262b3a"
        readonly property color statusUnknownBorder: "#666c88"
        readonly property color statusNotConfiguredForeground: "#9ea3b8"
        readonly property color statusNotConfiguredTint: "#262b3a"
        readonly property color statusNotConfiguredBorder: "#666c88"
        readonly property color statusOfflineForeground: "#a3adc2"
        readonly property color statusOfflineTint: "#252c3b"
        readonly property color statusOfflineBorder: "#5e6a82"
        readonly property color statusPendingForeground: "#f0b26a"
        readonly property color statusPendingTint: "#33302e"
        readonly property color statusPendingBorder: "#87694a"
        readonly property color statusRunningForeground: "#7adbc3"
        readonly property color statusRunningTint: "#1d3638"
        readonly property color statusRunningBorder: "#3f7a70"
        readonly property color statusBlockedForeground: "#f4ab84"
        readonly property color statusBlockedTint: "#352f30"
        readonly property color statusBlockedBorder: "#86644f"
        readonly property color statusFailedForeground: "#ff8a85"
        readonly property color statusFailedTint: "#3a2a33"
        readonly property color statusFailedBorder: "#a05a5e"
        readonly property color statusSucceededForeground: "#6fd59c"
        readonly property color statusSucceededTint: "#1e3631"
        readonly property color statusSucceededBorder: "#3e7a5e"
        readonly property color statusDegradedForeground: "#e2c972"
        readonly property color statusDegradedTint: "#33342c"
        readonly property color statusDegradedBorder: "#766d47"
        readonly property color statusApprovalRequiredForeground: "#c0b4ff"
        readonly property color statusApprovalRequiredTint: "#2e2c4c"
        readonly property color statusApprovalRequiredBorder: "#6f68a8"
    }

    readonly property QtObject atelierJour: QtObject {
        readonly property bool isDark: false
        readonly property string family: "atelier"
        readonly property color statusUnknownForeground: "#5a5970"
        readonly property color statusUnknownTint: "#efedf2"
        readonly property color statusUnknownBorder: "#8a889c"
        readonly property color statusNotConfiguredForeground: "#5a5970"
        readonly property color statusNotConfiguredTint: "#efedf2"
        readonly property color statusNotConfiguredBorder: "#8a889c"
        readonly property color statusOfflineForeground: "#4e5a6e"
        readonly property color statusOfflineTint: "#ebeef2"
        readonly property color statusOfflineBorder: "#87909f"
        readonly property color statusPendingForeground: "#8c4b0e"
        readonly property color statusPendingTint: "#f6ece2"
        readonly property color statusPendingBorder: "#b98a5f"
        readonly property color statusRunningForeground: "#0a6b5c"
        readonly property color statusRunningTint: "#e1f2ec"
        readonly property color statusRunningBorder: "#5a9d8c"
        readonly property color statusBlockedForeground: "#a1421b"
        readonly property color statusBlockedTint: "#f7ebe5"
        readonly property color statusBlockedBorder: "#c07f64"
        readonly property color statusFailedForeground: "#a6302f"
        readonly property color statusFailedTint: "#f8e9e9"
        readonly property color statusFailedBorder: "#c97f7d"
        readonly property color statusSucceededForeground: "#1f6a43"
        readonly property color statusSucceededTint: "#e6f2ea"
        readonly property color statusSucceededBorder: "#66997e"
        readonly property color statusDegradedForeground: "#6b550c"
        readonly property color statusDegradedTint: "#f3efe2"
        readonly property color statusDegradedBorder: "#9d8e5e"
        readonly property color statusApprovalRequiredForeground: "#4f3fb0"
        readonly property color statusApprovalRequiredTint: "#ece8fb"
        readonly property color statusApprovalRequiredBorder: "#9086cf"
    }

    readonly property QtObject studioGraphite: QtObject {
        readonly property bool isDark: true
        readonly property string family: "studio"
        readonly property color statusUnknownForeground: "#93a3a8"
        readonly property color statusUnknownTint: "#2b363b"
        readonly property color statusUnknownBorder: "#626f74"
        readonly property color statusNotConfiguredForeground: "#93a3a8"
        readonly property color statusNotConfiguredTint: "#2b363b"
        readonly property color statusNotConfiguredBorder: "#626f74"
        readonly property color statusOfflineForeground: "#9aabb5"
        readonly property color statusOfflineTint: "#2c373d"
        readonly property color statusOfflineBorder: "#616f76"
        readonly property color statusPendingForeground: "#e6a15a"
        readonly property color statusPendingTint: "#38352e"
        readonly property color statusPendingBorder: "#856745"
        readonly property color statusRunningForeground: "#63d7ce"
        readonly property color statusRunningTint: "#233e41"
        readonly property color statusRunningBorder: "#3d7675"
        readonly property color statusBlockedForeground: "#f2a97e"
        readonly property color statusBlockedTint: "#3a3734"
        readonly property color statusBlockedBorder: "#846754"
        readonly property color statusFailedForeground: "#f17b73"
        readonly property color statusFailedTint: "#3a2f32"
        readonly property color statusFailedBorder: "#9c5a57"
        readonly property color statusSucceededForeground: "#5fca91"
        readonly property color statusSucceededTint: "#233c37"
        readonly property color statusSucceededBorder: "#3f795f"
        readonly property color statusDegradedForeground: "#dcc26a"
        readonly property color statusDegradedTint: "#373b31"
        readonly property color statusDegradedBorder: "#756e49"
        readonly property color statusApprovalRequiredForeground: "#b3a4f5"
        readonly property color statusApprovalRequiredTint: "#303647"
        readonly property color statusApprovalRequiredBorder: "#6b6894"
    }

    readonly property QtObject studioPapier: QtObject {
        readonly property bool isDark: false
        readonly property string family: "studio"
        readonly property color statusUnknownForeground: "#5b6b6f"
        readonly property color statusUnknownTint: "#eff0f1"
        readonly property color statusUnknownBorder: "#8b9699"
        readonly property color statusNotConfiguredForeground: "#5b6b6f"
        readonly property color statusNotConfiguredTint: "#eff0f1"
        readonly property color statusNotConfiguredBorder: "#8b9699"
        readonly property color statusOfflineForeground: "#4f6270"
        readonly property color statusOfflineTint: "#edeff1"
        readonly property color statusOfflineBorder: "#89969f"
        readonly property color statusPendingForeground: "#8f4d10"
        readonly property color statusPendingTint: "#f4ede7"
        readonly property color statusPendingBorder: "#b68b64"
        readonly property color statusRunningForeground: "#0a6d68"
        readonly property color statusRunningTint: "#e6f0f0"
        readonly property color statusRunningBorder: "#5d9f9b"
        readonly property color statusBlockedForeground: "#a4441c"
        readonly property color statusBlockedTint: "#f6ece8"
        readonly property color statusBlockedBorder: "#c4856b"
        readonly property color statusFailedForeground: "#a83731"
        readonly property color statusFailedTint: "#f6ebea"
        readonly property color statusFailedBorder: "#c8817d"
        readonly property color statusSucceededForeground: "#216b45"
        readonly property color statusSucceededTint: "#e9f0ec"
        readonly property color statusSucceededBorder: "#6f9f86"
        readonly property color statusDegradedForeground: "#6e570d"
        readonly property color statusDegradedTint: "#f0eee7"
        readonly property color statusDegradedBorder: "#a29364"
        readonly property color statusApprovalRequiredForeground: "#54449f"
        readonly property color statusApprovalRequiredTint: "#eeecf5"
        readonly property color statusApprovalRequiredBorder: "#978dc4"
    }

    // Accesseurs plats : un composant ne choisit jamais son thème lui-même.
    readonly property color statusUnknownForeground: root.current.statusUnknownForeground
    readonly property color statusUnknownTint: root.current.statusUnknownTint
    readonly property color statusUnknownBorder: root.current.statusUnknownBorder
    readonly property color statusNotConfiguredForeground: root.current.statusNotConfiguredForeground
    readonly property color statusNotConfiguredTint: root.current.statusNotConfiguredTint
    readonly property color statusNotConfiguredBorder: root.current.statusNotConfiguredBorder
    readonly property color statusOfflineForeground: root.current.statusOfflineForeground
    readonly property color statusOfflineTint: root.current.statusOfflineTint
    readonly property color statusOfflineBorder: root.current.statusOfflineBorder
    readonly property color statusPendingForeground: root.current.statusPendingForeground
    readonly property color statusPendingTint: root.current.statusPendingTint
    readonly property color statusPendingBorder: root.current.statusPendingBorder
    readonly property color statusRunningForeground: root.current.statusRunningForeground
    readonly property color statusRunningTint: root.current.statusRunningTint
    readonly property color statusRunningBorder: root.current.statusRunningBorder
    readonly property color statusBlockedForeground: root.current.statusBlockedForeground
    readonly property color statusBlockedTint: root.current.statusBlockedTint
    readonly property color statusBlockedBorder: root.current.statusBlockedBorder
    readonly property color statusFailedForeground: root.current.statusFailedForeground
    readonly property color statusFailedTint: root.current.statusFailedTint
    readonly property color statusFailedBorder: root.current.statusFailedBorder
    readonly property color statusSucceededForeground: root.current.statusSucceededForeground
    readonly property color statusSucceededTint: root.current.statusSucceededTint
    readonly property color statusSucceededBorder: root.current.statusSucceededBorder
    readonly property color statusDegradedForeground: root.current.statusDegradedForeground
    readonly property color statusDegradedTint: root.current.statusDegradedTint
    readonly property color statusDegradedBorder: root.current.statusDegradedBorder
    readonly property color statusApprovalRequiredForeground: root.current.statusApprovalRequiredForeground
    readonly property color statusApprovalRequiredTint: root.current.statusApprovalRequiredTint
    readonly property color statusApprovalRequiredBorder: root.current.statusApprovalRequiredBorder

    // Métadonnées d'état : la couleur n'est jamais seule porteuse de sens.
    readonly property QtObject meta: QtObject {
        readonly property QtObject unknown: QtObject {
            readonly property string key: "unknown"
            readonly property string label: "Inconnu"
            readonly property string glyphName: "question"
            readonly property string asciiFallback: "?"
            readonly property bool dashedBorder: true
            readonly property bool animated: false
            readonly property bool neverFilled: true
            readonly property color foreground: root.statusUnknownForeground
            readonly property color tint: root.statusUnknownTint
            readonly property color border: root.statusUnknownBorder
        }
        readonly property QtObject notConfigured: QtObject {
            readonly property string key: "notConfigured"
            readonly property string label: "Non configuré"
            readonly property string glyphName: "unplugged"
            readonly property string asciiFallback: "-"
            readonly property bool dashedBorder: true
            readonly property bool animated: false
            readonly property bool neverFilled: true
            readonly property color foreground: root.statusNotConfiguredForeground
            readonly property color tint: root.statusNotConfiguredTint
            readonly property color border: root.statusNotConfiguredBorder
        }
        readonly property QtObject offline: QtObject {
            readonly property string key: "offline"
            readonly property string label: "Hors ligne"
            readonly property string glyphName: "link-broken"
            readonly property string asciiFallback: "//"
            readonly property bool dashedBorder: true
            readonly property bool animated: false
            readonly property bool neverFilled: true
            readonly property color foreground: root.statusOfflineForeground
            readonly property color tint: root.statusOfflineTint
            readonly property color border: root.statusOfflineBorder
        }
        readonly property QtObject pending: QtObject {
            readonly property string key: "pending"
            readonly property string label: "En attente"
            readonly property string glyphName: "queue"
            readonly property string asciiFallback: ".."
            readonly property bool dashedBorder: false
            readonly property bool animated: false
            readonly property bool neverFilled: false
            readonly property color foreground: root.statusPendingForeground
            readonly property color tint: root.statusPendingTint
            readonly property color border: root.statusPendingBorder
        }
        readonly property QtObject running: QtObject {
            readonly property string key: "running"
            readonly property string label: "En cours"
            readonly property string glyphName: "activity"
            readonly property string asciiFallback: ">"
            readonly property bool dashedBorder: false
            readonly property bool animated: true
            readonly property bool neverFilled: false
            readonly property color foreground: root.statusRunningForeground
            readonly property color tint: root.statusRunningTint
            readonly property color border: root.statusRunningBorder
        }
        readonly property QtObject blocked: QtObject {
            readonly property string key: "blocked"
            readonly property string label: "Bloqué"
            readonly property string glyphName: "barrier"
            readonly property string asciiFallback: "!"
            readonly property bool dashedBorder: false
            readonly property bool animated: false
            readonly property bool neverFilled: false
            readonly property color foreground: root.statusBlockedForeground
            readonly property color tint: root.statusBlockedTint
            readonly property color border: root.statusBlockedBorder
        }
        readonly property QtObject failed: QtObject {
            readonly property string key: "failed"
            readonly property string label: "En échec"
            readonly property string glyphName: "cross"
            readonly property string asciiFallback: "x"
            readonly property bool dashedBorder: false
            readonly property bool animated: false
            readonly property bool neverFilled: false
            readonly property color foreground: root.statusFailedForeground
            readonly property color tint: root.statusFailedTint
            readonly property color border: root.statusFailedBorder
        }
        readonly property QtObject succeeded: QtObject {
            readonly property string key: "succeeded"
            readonly property string label: "Réussi"
            readonly property string glyphName: "check"
            readonly property string asciiFallback: "v"
            readonly property bool dashedBorder: false
            readonly property bool animated: false
            readonly property bool neverFilled: false
            readonly property color foreground: root.statusSucceededForeground
            readonly property color tint: root.statusSucceededTint
            readonly property color border: root.statusSucceededBorder
        }
        readonly property QtObject degraded: QtObject {
            readonly property string key: "degraded"
            readonly property string label: "Dégradé"
            readonly property string glyphName: "warning"
            readonly property string asciiFallback: "~"
            readonly property bool dashedBorder: false
            readonly property bool animated: false
            readonly property bool neverFilled: true
            readonly property color foreground: root.statusDegradedForeground
            readonly property color tint: root.statusDegradedTint
            readonly property color border: root.statusDegradedBorder
        }
        readonly property QtObject approvalRequired: QtObject {
            readonly property string key: "approvalRequired"
            readonly property string label: "Approbation requise"
            readonly property string glyphName: "hand-raised"
            readonly property string asciiFallback: "?!"
            readonly property bool dashedBorder: false
            readonly property bool animated: false
            readonly property bool neverFilled: false
            readonly property color foreground: root.statusApprovalRequiredForeground
            readonly property color tint: root.statusApprovalRequiredTint
            readonly property color border: root.statusApprovalRequiredBorder
        }
    }

    // Ordre d'agrégation : une réussite ne masque jamais un échec du groupe.
    readonly property var priorityOrder: ["failed", "blocked", "approvalRequired", "degraded", "offline", "running", "pending", "notConfigured", "unknown", "succeeded"]

    // Correspondance relevée dans le backend ; voir $backendMapping.$sources.
    readonly property var backendMapping: ({
        "runStatus": {
            "pending": { "token": "pending", "label": "En attente" },
            "queued": { "token": "pending", "label": "En file" },
            "preparing": { "token": "running", "label": "Préparation" },
            "running": { "token": "running", "label": "En cours" },
            "waiting_approval": { "token": "approvalRequired", "label": "Approbation requise" },
            "stopping": { "token": "running", "label": "Arrêt en cours" },
            "blocked": { "token": "blocked", "label": "Bloqué" },
            "succeeded": { "token": "succeeded", "label": "Réussi" },
            "failed": { "token": "failed", "label": "En échec" },
            "cancelled": { "token": "unknown", "label": "Annulé" },
            "interrupted": { "token": "blocked", "label": "Interrompu" }
        },
        "taskStatus": {
            "backlog": { "token": "unknown", "label": "En attente de tri" },
            "queued": { "token": "pending", "label": "En file" },
            "planning": { "token": "running", "label": "Planification" },
            "in_progress": { "token": "running", "label": "En cours" },
            "review": { "token": "approvalRequired", "label": "En revue" },
            "blocked": { "token": "blocked", "label": "Bloqué" },
            "done": { "token": "succeeded", "label": "Terminé" },
            "failed": { "token": "failed", "label": "En échec" }
        },
        "gatewayDiagnostic": {
            "not_configured": { "token": "notConfigured", "label": "Non configuré" },
            "ready": { "token": "succeeded", "label": "Prêt" },
            "unauthorized": { "token": "failed", "label": "Accès refusé" },
            "timeout": { "token": "offline", "label": "Délai dépassé" },
            "unavailable": { "token": "offline", "label": "Indisponible" },
            "incompatible_version": { "token": "degraded", "label": "Version incompatible" },
            "invalid_response": { "token": "degraded", "label": "Réponse inexploitable" }
        },
        "readiness": {
            "ready": { "token": "succeeded", "label": "Prêt" },
            "degraded": { "token": "degraded", "label": "Dégradé" }
        },
        "clientTransport": {
            "disconnected": { "token": "offline", "label": "Hors ligne" },
            "reconnecting": { "token": "pending", "label": "Reconnexion" },
            "no_sample": { "token": "unknown", "label": "Inconnu" }
        }
    })

    /*!
        Résout un identifiant d'état brut de l'API vers son jeu de jetons.
        Un état inconnu du backend ne provoque ni plantage ni invention :
        il retombe sur « Inconnu » en conservant l'identifiant brut.
    */
    function resolve(family, rawState) {
        var table = root.backendMapping[family];
        if (table !== undefined && table[rawState] !== undefined) {
            var row = table[rawState];
            return {
                "token": row.token,
                "label": row.label,
                "meta": root.meta[row.token],
                "recognised": true
            };
        }
        return {
            "token": "unknown",
            "label": root.meta.unknown.label,
            "meta": root.meta.unknown,
            "recognised": false
        };
    }
}
