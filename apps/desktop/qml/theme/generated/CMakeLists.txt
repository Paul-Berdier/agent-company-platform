# Acp.Design — singletons de design ENGENDRÉS depuis design/tokens/*.json.
#
# Aucun de ces fichiers ne se modifie à la main. La commande de régénération est :
#
#   python apps/desktop/cmake/generate_design_tokens.py \
#       --tokens design/tokens --out apps/desktop/qml/theme/generated
#
# La cible `acp_check_design_tokens` échoue si la sortie versionnée est périmée.

set(ACP_DESIGN_SINGLETONS
    Colors.qml
    Status.qml
    Type.qml
    Space.qml
    Radius.qml
    Elevation.qml
    Motion.qml
)

# Deux conditions sont nécessaires pour qu'un fichier QML soit un singleton : le
# « pragma Singleton » dans le fichier — que le générateur écrit — ET cette propriété de
# source, posée AVANT la création du module. Sans elle, le type serait ordinaire et
# l'erreur n'apparaîtrait qu'à l'exécution.
acp_mark_qml_singletons(${ACP_DESIGN_SINGLETONS})

acp_add_qml_module(
    TARGET acp_design
    URI Acp.Design
    QML_FILES ${ACP_DESIGN_SINGLETONS}
)
