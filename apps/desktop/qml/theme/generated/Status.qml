// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/semantic-status.json (version 1.0.0)
// Palettes  : design/tokens/desktop-palettes.json
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root

    // Thème actif. Écrit par ThemeBridge au démarrage et à
    // chaque changement de préférence ; jamais deviné par un composant.
    property string theme: "dark"
    readonly property bool isDark: theme !== "light"

    property string family: "pixel"
    readonly property bool isPixel: family !== "studio"
    readonly property string familyLabel: root.isPixel ? "Pixel Atelier" : "Studio"
    readonly property string variantLabel: root.isPixel
        ? (root.isDark ? "Pixel Atelier Nuit" : "Pixel Atelier Jour")
        : (root.isDark ? "Studio Graphite" : "Studio Papier")

    readonly property QtObject pixelDark: QtObject {
        readonly property color statusUnknownForeground: "#b1b8ca"
        readonly property color statusUnknownTint: "#2c3343"
        readonly property color statusUnknownBorder: "#8e99ae"
        readonly property color statusNotConfiguredForeground: "#b1b8ca"
        readonly property color statusNotConfiguredTint: "#2c3343"
        readonly property color statusNotConfiguredBorder: "#8e99ae"
        readonly property color statusOfflineForeground: "#b5bdce"
        readonly property color statusOfflineTint: "#2c3343"
        readonly property color statusOfflineBorder: "#8e99ae"
        readonly property color statusPendingForeground: "#e5ba79"
        readonly property color statusPendingTint: "#393226"
        readonly property color statusPendingBorder: "#bd9861"
        readonly property color statusRunningForeground: "#7adbc3"
        readonly property color statusRunningTint: "#213a36"
        readonly property color statusRunningBorder: "#70bba9"
        readonly property color statusBlockedForeground: "#eab18d"
        readonly property color statusBlockedTint: "#3a302c"
        readonly property color statusBlockedBorder: "#be9279"
        readonly property color statusFailedForeground: "#eda1a2"
        readonly property color statusFailedTint: "#3d2b34"
        readonly property color statusFailedBorder: "#c0868d"
        readonly property color statusSucceededForeground: "#98d2ae"
        readonly property color statusSucceededTint: "#25382f"
        readonly property color statusSucceededBorder: "#7fb18e"
        readonly property color statusDegradedForeground: "#ddc386"
        readonly property color statusDegradedTint: "#373428"
        readonly property color statusDegradedBorder: "#b4a269"
        readonly property color statusApprovalRequiredForeground: "#f0c58b"
        readonly property color statusApprovalRequiredTint: "#3d3228"
        readonly property color statusApprovalRequiredBorder: "#c39d6d"
    }

    readonly property QtObject pixelLight: QtObject {
        readonly property color statusUnknownForeground: "#535b71"
        readonly property color statusUnknownTint: "#ececf2"
        readonly property color statusUnknownBorder: "#767d91"
        readonly property color statusNotConfiguredForeground: "#535b71"
        readonly property color statusNotConfiguredTint: "#ececf2"
        readonly property color statusNotConfiguredBorder: "#767d91"
        readonly property color statusOfflineForeground: "#505d70"
        readonly property color statusOfflineTint: "#e9edf1"
        readonly property color statusOfflineBorder: "#758192"
        readonly property color statusPendingForeground: "#82551f"
        readonly property color statusPendingTint: "#f6ede0"
        readonly property color statusPendingBorder: "#9b7544"
        readonly property color statusRunningForeground: "#226d5e"
        readonly property color statusRunningTint: "#e4f1eb"
        readonly property color statusRunningBorder: "#478d7d"
        readonly property color statusBlockedForeground: "#964923"
        readonly property color statusBlockedTint: "#f6eae2"
        readonly property color statusBlockedBorder: "#b7795a"
        readonly property color statusFailedForeground: "#a13d49"
        readonly property color statusFailedTint: "#f8e8e9"
        readonly property color statusFailedBorder: "#b46c74"
        readonly property color statusSucceededForeground: "#316c49"
        readonly property color statusSucceededTint: "#e6f0e8"
        readonly property color statusSucceededBorder: "#638d71"
        readonly property color statusDegradedForeground: "#786024"
        readonly property color statusDegradedTint: "#f1eede"
        readonly property color statusDegradedBorder: "#978552"
        readonly property color statusApprovalRequiredForeground: "#865520"
        readonly property color statusApprovalRequiredTint: "#f7eddc"
        readonly property color statusApprovalRequiredBorder: "#a17840"
    }

    readonly property QtObject studioDark: QtObject {
        readonly property color statusUnknownForeground: "#b1b8ca"
        readonly property color statusUnknownTint: "#2c3343"
        readonly property color statusUnknownBorder: "#8e99ae"
        readonly property color statusNotConfiguredForeground: "#b1b8ca"
        readonly property color statusNotConfiguredTint: "#2c3343"
        readonly property color statusNotConfiguredBorder: "#8e99ae"
        readonly property color statusOfflineForeground: "#b5bdce"
        readonly property color statusOfflineTint: "#2c3343"
        readonly property color statusOfflineBorder: "#8e99ae"
        readonly property color statusPendingForeground: "#e5ba79"
        readonly property color statusPendingTint: "#393226"
        readonly property color statusPendingBorder: "#bd9861"
        readonly property color statusRunningForeground: "#7adbc3"
        readonly property color statusRunningTint: "#213a36"
        readonly property color statusRunningBorder: "#70bba9"
        readonly property color statusBlockedForeground: "#eab18d"
        readonly property color statusBlockedTint: "#3a302c"
        readonly property color statusBlockedBorder: "#be9279"
        readonly property color statusFailedForeground: "#eda1a2"
        readonly property color statusFailedTint: "#3d2b34"
        readonly property color statusFailedBorder: "#c0868d"
        readonly property color statusSucceededForeground: "#98d2ae"
        readonly property color statusSucceededTint: "#25382f"
        readonly property color statusSucceededBorder: "#7fb18e"
        readonly property color statusDegradedForeground: "#ddc386"
        readonly property color statusDegradedTint: "#373428"
        readonly property color statusDegradedBorder: "#b4a269"
        readonly property color statusApprovalRequiredForeground: "#f0c58b"
        readonly property color statusApprovalRequiredTint: "#3d3228"
        readonly property color statusApprovalRequiredBorder: "#c39d6d"
    }

    readonly property QtObject studioLight: QtObject {
        readonly property color statusUnknownForeground: "#535b71"
        readonly property color statusUnknownTint: "#ececf2"
        readonly property color statusUnknownBorder: "#767d91"
        readonly property color statusNotConfiguredForeground: "#535b71"
        readonly property color statusNotConfiguredTint: "#ececf2"
        readonly property color statusNotConfiguredBorder: "#767d91"
        readonly property color statusOfflineForeground: "#505d70"
        readonly property color statusOfflineTint: "#e9edf1"
        readonly property color statusOfflineBorder: "#758192"
        readonly property color statusPendingForeground: "#82551f"
        readonly property color statusPendingTint: "#f6ede0"
        readonly property color statusPendingBorder: "#9b7544"
        readonly property color statusRunningForeground: "#226d5e"
        readonly property color statusRunningTint: "#e4f1eb"
        readonly property color statusRunningBorder: "#478d7d"
        readonly property color statusBlockedForeground: "#964923"
        readonly property color statusBlockedTint: "#f6eae2"
        readonly property color statusBlockedBorder: "#b7795a"
        readonly property color statusFailedForeground: "#a13d49"
        readonly property color statusFailedTint: "#f8e8e9"
        readonly property color statusFailedBorder: "#b46c74"
        readonly property color statusSucceededForeground: "#316c49"
        readonly property color statusSucceededTint: "#e6f0e8"
        readonly property color statusSucceededBorder: "#638d71"
        readonly property color statusDegradedForeground: "#786024"
        readonly property color statusDegradedTint: "#f1eede"
        readonly property color statusDegradedBorder: "#978552"
        readonly property color statusApprovalRequiredForeground: "#865520"
        readonly property color statusApprovalRequiredTint: "#f7eddc"
        readonly property color statusApprovalRequiredBorder: "#a17840"
    }

    readonly property QtObject dark: root.isPixel ? root.pixelDark : root.studioDark
    readonly property QtObject light: root.isPixel ? root.pixelLight : root.studioLight

    readonly property color statusUnknownForeground: (root.isDark ? root.dark : root.light).statusUnknownForeground
    readonly property color statusUnknownTint: (root.isDark ? root.dark : root.light).statusUnknownTint
    readonly property color statusUnknownBorder: (root.isDark ? root.dark : root.light).statusUnknownBorder
    readonly property color statusNotConfiguredForeground: (root.isDark ? root.dark : root.light).statusNotConfiguredForeground
    readonly property color statusNotConfiguredTint: (root.isDark ? root.dark : root.light).statusNotConfiguredTint
    readonly property color statusNotConfiguredBorder: (root.isDark ? root.dark : root.light).statusNotConfiguredBorder
    readonly property color statusOfflineForeground: (root.isDark ? root.dark : root.light).statusOfflineForeground
    readonly property color statusOfflineTint: (root.isDark ? root.dark : root.light).statusOfflineTint
    readonly property color statusOfflineBorder: (root.isDark ? root.dark : root.light).statusOfflineBorder
    readonly property color statusPendingForeground: (root.isDark ? root.dark : root.light).statusPendingForeground
    readonly property color statusPendingTint: (root.isDark ? root.dark : root.light).statusPendingTint
    readonly property color statusPendingBorder: (root.isDark ? root.dark : root.light).statusPendingBorder
    readonly property color statusRunningForeground: (root.isDark ? root.dark : root.light).statusRunningForeground
    readonly property color statusRunningTint: (root.isDark ? root.dark : root.light).statusRunningTint
    readonly property color statusRunningBorder: (root.isDark ? root.dark : root.light).statusRunningBorder
    readonly property color statusBlockedForeground: (root.isDark ? root.dark : root.light).statusBlockedForeground
    readonly property color statusBlockedTint: (root.isDark ? root.dark : root.light).statusBlockedTint
    readonly property color statusBlockedBorder: (root.isDark ? root.dark : root.light).statusBlockedBorder
    readonly property color statusFailedForeground: (root.isDark ? root.dark : root.light).statusFailedForeground
    readonly property color statusFailedTint: (root.isDark ? root.dark : root.light).statusFailedTint
    readonly property color statusFailedBorder: (root.isDark ? root.dark : root.light).statusFailedBorder
    readonly property color statusSucceededForeground: (root.isDark ? root.dark : root.light).statusSucceededForeground
    readonly property color statusSucceededTint: (root.isDark ? root.dark : root.light).statusSucceededTint
    readonly property color statusSucceededBorder: (root.isDark ? root.dark : root.light).statusSucceededBorder
    readonly property color statusDegradedForeground: (root.isDark ? root.dark : root.light).statusDegradedForeground
    readonly property color statusDegradedTint: (root.isDark ? root.dark : root.light).statusDegradedTint
    readonly property color statusDegradedBorder: (root.isDark ? root.dark : root.light).statusDegradedBorder
    readonly property color statusApprovalRequiredForeground: (root.isDark ? root.dark : root.light).statusApprovalRequiredForeground
    readonly property color statusApprovalRequiredTint: (root.isDark ? root.dark : root.light).statusApprovalRequiredTint
    readonly property color statusApprovalRequiredBorder: (root.isDark ? root.dark : root.light).statusApprovalRequiredBorder

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
