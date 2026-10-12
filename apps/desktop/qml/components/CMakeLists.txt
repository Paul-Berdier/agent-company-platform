# Acp.Components — composants composites : états, pastilles, lignes de valeurs.

acp_add_qml_module(
    TARGET acp_components
    URI Acp.Components
    QML_FILES
        AtelierMark.qml
        AtelierScene.qml
        BandeauMessage.qml
        BlocTexte.qml
        BulleMessage.qml
        Carte.qml
        EmptyState.qml
        ExecutionDetails.qml
        HermesConnectionCard.qml
        EtatLecture.qml
        KeyValueRow.qml
        PastilleCompteur.qml
        QuotaGauge.qml
        SectionHeader.qml
        StatusChip.qml
)

# Le pack sous licence reste local ; chaque clone sans import dispose du décor ACP original.
set(atelier_scene "${CMAKE_CURRENT_SOURCE_DIR}/../../resources/images/atelier-fallback.png")
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../../resources/atelier-local/atelier-scene.png")
    set(atelier_scene "${CMAKE_CURRENT_SOURCE_DIR}/../../resources/atelier-local/atelier-scene.png")
endif()
set_source_files_properties("${atelier_scene}" PROPERTIES QT_RESOURCE_ALIAS "atelier.png")
set(atelier_icon "${CMAKE_CURRENT_SOURCE_DIR}/../../resources/icons/acp-atelier.png")
set_source_files_properties("${atelier_icon}" PROPERTIES QT_RESOURCE_ALIAS "icon.png")
qt_add_resources(acp_components "atelier_images" PREFIX "/atelier" FILES "${atelier_scene}" "${atelier_icon}")
