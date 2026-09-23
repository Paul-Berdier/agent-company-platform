# Fabrique un module QML statique de la station.
#
# Un module par répertoire de QML, et un URI par module. C'est plus verbeux qu'un module
# unique contenant des sous-répertoires, mais c'est sans ambiguïté : chaque `import` d'un
# fichier QML désigne exactement un répertoire du dépôt, et la règle documentée par Qt —
# « la structure du répertoire source doit correspondre au chemin cible de l'URI » — est
# tenue littéralement.
#
# Les modules sont statiques et leur greffon est lié à l'exécutable : c'est la forme
# documentée pour qu'un module QML statique soit enregistré au démarrage.

function(acp_add_qml_module)
    set(options "")
    set(one_value_args TARGET URI)
    set(multi_value_args QML_FILES IMPORTS DEPENDS)
    cmake_parse_arguments(ARG "${options}" "${one_value_args}" "${multi_value_args}" ${ARGN})

    if(NOT ARG_TARGET OR NOT ARG_URI)
        message(FATAL_ERROR "acp_add_qml_module : TARGET et URI sont obligatoires.")
    endif()
    if(NOT ARG_QML_FILES)
        message(FATAL_ERROR "acp_add_qml_module(${ARG_TARGET}) : aucun fichier QML fourni.")
    endif()

    # Chaque fichier déclaré doit exister : un chemin périmé dans CMake produirait sinon
    # un module amputé qui ne se signale qu'à l'exécution.
    foreach(qml_file IN LISTS ARG_QML_FILES)
        if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${qml_file}")
            message(FATAL_ERROR
                "acp_add_qml_module(${ARG_TARGET}) : fichier QML déclaré mais absent — "
                "${CMAKE_CURRENT_SOURCE_DIR}/${qml_file}")
        endif()
    endforeach()

    qt_add_library(${ARG_TARGET} STATIC)

    qt_add_qml_module(${ARG_TARGET}
        URI ${ARG_URI}
        VERSION 1.0
        QML_FILES ${ARG_QML_FILES}
        IMPORTS ${ARG_IMPORTS}
    )

    target_link_libraries(${ARG_TARGET} PRIVATE Qt6::Quick)
    if(ARG_DEPENDS)
        target_link_libraries(${ARG_TARGET} PRIVATE ${ARG_DEPENDS})
    endif()
endfunction()

# Marque des fichiers QML comme singletons.
#
# Qt exige DEUX choses pour un singleton QML : « pragma Singleton » dans le fichier ET la
# propriété de source QT_QML_SINGLETON_TYPE à TRUE, posée AVANT la création du module.
# Oublier la seconde produit un type ordinaire, et l'erreur n'apparaît qu'à l'exécution.
function(acp_mark_qml_singletons)
    foreach(qml_file IN LISTS ARGN)
        set_source_files_properties(${qml_file} PROPERTIES QT_QML_SINGLETON_TYPE TRUE)
    endforeach()
endfunction()
