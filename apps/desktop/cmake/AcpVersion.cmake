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

# Lecture de l'épinglage de Hermes depuis hermes/contrat/HERMES_VERSION.
#
# C'est la source unique déjà vérifiée par l'intégration continue de l'image : la station
# n'y recopie aucune valeur à la main. Elle en tire la version de Hermes testée, la version
# et l'empreinte du contrat JSON-RPC épinglé, et le contrat attendu du greffon acp-poste.
# Une clé absente ou vide refuse la configuration : une station qui ne sait pas contre quoi
# elle a été testée ne doit pas prétendre le savoir.
#
# Variables posées dans la portée de l'appelant : ACP_HERMES_VERSION,
# ACP_OPENRPC_INFO_VERSION, ACP_OPENRPC_SHA256, ACP_CONTRAT_ACP_POSTE et ACP_OPENRPC_FILE
# (chemin absolu du contrat JSON-RPC épinglé, lu par les tests de conformité).
function(acp_read_hermes_contract)
    set(contract_dir "${CMAKE_CURRENT_SOURCE_DIR}/../../hermes/contrat")
    get_filename_component(contract_dir "${contract_dir}" ABSOLUTE)
    set(pin_file "${contract_dir}/HERMES_VERSION")
    set(openrpc_file "${contract_dir}/gateway-contract.openrpc.json")

    foreach(required_file IN ITEMS "${pin_file}" "${openrpc_file}")
        if(NOT EXISTS "${required_file}")
            message(FATAL_ERROR
                "Fichier du contrat de Hermes introuvable : ${required_file}. La station doit "
                "être configurée depuis le dépôt complet.")
        endif()
    endforeach()

    file(STRINGS "${pin_file}" pin_lines REGEX "^[A-Z0-9_]+=")
    foreach(key IN ITEMS HERMES_VERSION OPENRPC_INFO_VERSION OPENRPC_SHA256 CONTRAT_ACP_POSTE)
        set(value "")
        foreach(line IN LISTS pin_lines)
            if(line MATCHES "^${key}=(.*)$")
                set(value "${CMAKE_MATCH_1}")
            endif()
        endforeach()
        string(STRIP "${value}" value)
        if(value STREQUAL "")
            message(FATAL_ERROR
                "Clé ${key} absente ou vide dans ${pin_file} : configuration refusée.")
        endif()
        set(ACP_${key} "${value}" PARENT_SCOPE)
    endforeach()

    set(ACP_OPENRPC_FILE "${openrpc_file}" PARENT_SCOPE)
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${pin_file}")
endfunction()
