# Lecture de la version du produit depuis le fichier VERSION de la racine du dépôt.
#
# L'audit demande explicitement que la station ne dérive pas silencieusement de VERSION
# (section 6.3, point 7). Le numéro n'est donc écrit qu'UNE fois, dans le fichier de la
# racine, et toute autre occurrence est engendrée.

function(acp_read_product_version out_variable)
    set(version_file "${CMAKE_CURRENT_SOURCE_DIR}/../../VERSION")
    get_filename_component(version_file "${version_file}" ABSOLUTE)

    if(NOT EXISTS "${version_file}")
        message(FATAL_ERROR
            "Fichier VERSION introuvable : ${version_file}. "
            "La station doit être configurée depuis le dépôt complet ; elle refuse de se "
            "donner un numéro de version inventé.")
    endif()

    file(READ "${version_file}" raw_version)
    string(STRIP "${raw_version}" raw_version)

    if(NOT raw_version MATCHES "^[0-9]+\\.[0-9]+\\.[0-9]+$")
        message(FATAL_ERROR
            "Le fichier VERSION contient « ${raw_version} », qui n'est pas de la forme "
            "majeur.mineur.correctif. Configuration refusée.")
    endif()

    set(${out_variable} "${raw_version}" PARENT_SCOPE)

    # Le fichier VERSION devient une dépendance de la configuration : le modifier
    # déclenche une reconfiguration, et la version embarquée ne peut pas se périmer.
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${version_file}")
endfunction()
