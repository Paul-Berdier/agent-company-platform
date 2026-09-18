# Acp.Theme — passerelle entre la préférence d'apparence et les singletons générés.

add_subdirectory(generated)

acp_add_qml_module(
    TARGET acp_theme
    URI Acp.Theme
    QML_FILES ThemeBridge.qml
)
