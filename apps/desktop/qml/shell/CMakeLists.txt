# Acp.Station — coquille : barres, navigation, zone de travail, inspecteur, palette.

acp_add_qml_module(
    TARGET acp_station
    URI Acp.Station
    QML_FILES
        CommandPalette.qml
        InspectorPanel.qml
        ShellRoot.qml
        SideNavigation.qml
        StatusBar.qml
        TopBar.qml
        WorkArea.qml
)
