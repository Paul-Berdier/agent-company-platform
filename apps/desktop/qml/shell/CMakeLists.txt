# Acp.Station — coquille : barres, navigation, zone de travail, panneau des agents, volet bas,
# palette.

acp_add_qml_module(
    TARGET acp_station
    URI Acp.Station
    QML_FILES
        AgentsPanel.qml
        BottomDrawer.qml
        CommandPalette.qml
        LigneArbre.qml
        ShellRoot.qml
        SideNavigation.qml
        StatusBar.qml
        TopBar.qml
        WorkArea.qml
)
