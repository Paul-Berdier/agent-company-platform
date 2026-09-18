# Station de travail native — Agent Company Platform
#
# AVERTISSEMENT, à lire avant toute conclusion sur ce projet :
# ce fichier n'a JAMAIS été configuré, et aucune cible n'a jamais été compilée. Le poste
# de rédaction ne dispose ni de Qt, ni de CMake, ni de Ninja, ni de MSVC, ni d'aucun
# compilateur C++ (relevé du 18 septembre 2026, docs/desktop-railway-audit.md, section
# 11.1). La seule preuve de compilation recevable viendra d'un job d'intégration continue
# Windows, qui n'existe pas encore.
#
# Version de CMake : 3.24 est exigée pour disposer de CMAKE_COMPILE_WARNING_AS_ERROR
# (introduite en 3.24) et d'un support de préréglages version 6. Qt 6.8 exige au minimum
# CMake 3.16 ; on demande davantage parce que le projet en utilise davantage.

cmake_minimum_required(VERSION 3.24)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
include(AcpVersion)
include(AcpQmlModule)

acp_read_product_version(ACP_DESKTOP_VERSION)

project(acp_desktop
    VERSION ${ACP_DESKTOP_VERSION}
    DESCRIPTION "Station de travail native de l'Agent Company Platform"
    LANGUAGES CXX
)

# --- Modules Qt ---------------------------------------------------------------
#
# Liste MINIMALE, chaque module justifié (voir docs/native-desktop-architecture.md) :
#   Core          objets, chaînes, JSON, minuteurs, réglages — indispensable ;
#   Gui           QGuiApplication et QStyleHints (thème système) ; requis par Quick ;
#   Qml           moteur QML, enregistrement des types, singletons ;
#   Quick         scène graphique déclarative ;
#   QuickControls2  SplitView, ToolTip, CheckBox, ApplicationWindow du style Basic ;
#   Network       QNetworkAccessManager, pot de cookies, flux SSE.
#
# Modules VOLONTAIREMENT absents :
#   Widgets       aucune fenêtre classique n'est employée ;
#   WebEngine     interdit par le cahier des charges, et de toute façon inutile ;
#   Charts, DataVisualization, VirtualKeyboard : non utilisés, et publiés sous GPL pour
#                 l'offre open source — donc incompatibles avec une distribution binaire
#                 propriétaire. Aucun d'eux n'est lié.
#
# Licence : les six modules retenus sont des modules « essentiels » de Qt, publiés sous
# LGPLv3 ou sous licence commerciale. Une distribution binaire sous LGPLv3 impose la
# liaison DYNAMIQUE, la fourniture du code source de Qt (ou une offre écrite), la
# possibilité pour l'utilisateur de relier une version modifiée, et la remise du texte de
# la licence. Ces obligations sont documentées ; elles n'ont PAS été validées
# juridiquement pour ce produit, et la question de la licence Qt reste ouverte (audit,
# question 18). Aucune liaison statique de Qt n'est configurée ici.

find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2 Network)

qt_standard_project_setup(REQUIRES 6.8)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(ACP_DESKTOP_BUILD_TESTS "Construire les cibles de test de la station" ON)
option(ACP_DESKTOP_REGENERATE_TOKENS
    "Régénérer les singletons QML de design à la configuration (exige Python 3)" OFF)

set(ACP_DESKTOP_QT_VERSION "${Qt6_VERSION}")
set(ACP_DESKTOP_BUILD_TYPE "${CMAKE_BUILD_TYPE}")
if(NOT ACP_DESKTOP_BUILD_TYPE)
    set(ACP_DESKTOP_BUILD_TYPE "multi-configuration")
endif()

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/src/app/BuildConfig.h.in"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/app/BuildConfig.h"
    @ONLY
)

# --- Jetons de design ---------------------------------------------------------
#
# La sortie du générateur est VERSIONNÉE : un poste sans Python peut configurer le projet.
# La cible `acp_check_design_tokens` vérifie qu'elle n'est pas périmée ; elle est destinée
# à l'intégration continue, pas au chemin de compilation nominal.

find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
    set(ACP_TOKEN_GENERATOR "${CMAKE_CURRENT_SOURCE_DIR}/cmake/generate_design_tokens.py")
    set(ACP_TOKEN_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../design/tokens")
    set(ACP_TOKEN_OUTPUT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/qml/theme/generated")

    add_custom_target(acp_check_design_tokens
        COMMAND ${Python3_EXECUTABLE} "${ACP_TOKEN_GENERATOR}"
                --tokens "${ACP_TOKEN_SOURCE_DIR}"
                --out "${ACP_TOKEN_OUTPUT_DIR}"
                --check
        COMMENT "Vérification que les singletons QML de design sont à jour"
        VERBATIM
    )

    if(ACP_DESKTOP_REGENERATE_TOKENS)
        execute_process(
            COMMAND ${Python3_EXECUTABLE} "${ACP_TOKEN_GENERATOR}"
                    --tokens "${ACP_TOKEN_SOURCE_DIR}"
                    --out "${ACP_TOKEN_OUTPUT_DIR}"
            RESULT_VARIABLE token_result
            OUTPUT_VARIABLE token_output
            ERROR_VARIABLE token_error
        )
        if(NOT token_result EQUAL 0)
            message(FATAL_ERROR
                "Génération des jetons de design refusée :\n${token_error}")
        endif()
        message(STATUS "Jetons de design régénérés : ${token_output}")
    endif()
else()
    message(STATUS
        "Python 3 est absent : la vérification des jetons de design ne sera pas "
        "disponible. La sortie versionnée est utilisée telle quelle.")
endif()

# --- Bibliothèque de logique --------------------------------------------------
#
# Toute la logique vit ici, SANS dépendance au module QML : les cibles de test la lient
# sans embarquer la scène graphique, et un défaut de transport se prouve sans ouvrir de
# fenêtre.

set(ACP_CORE_SOURCES
    src/app/QmlEnums.h
    src/commands/Command.h
    src/commands/CommandRegistry.cpp
    src/commands/CommandRegistry.h
    src/diagnostics/Redaction.cpp
    src/diagnostics/Redaction.h
    src/navigation/NavigationModel.cpp
    src/navigation/NavigationModel.h
    src/storage/SettingsStore.cpp
    src/storage/SettingsStore.h
    src/system/SystemAppearance.cpp
    src/system/SystemAppearance.h
)

qt_add_library(acp_core STATIC ${ACP_CORE_SOURCES})

target_include_directories(acp_core PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_BINARY_DIR}/generated"
)

target_link_libraries(acp_core PUBLIC
    Qt6::Core
    Qt6::Gui
    Qt6::Network
    Qt6::Qml
    Qt6::Quick
)

# Les conversions implicites de QString depuis un littéral ASCII sont désactivées : elles
# masquent des problèmes d'encodage, et tout le texte de ce produit est en français, donc
# accentué. QT_NO_FOREACH interdit la macro `foreach`, retirée du style Qt moderne.
#
# QT_DISABLE_DEPRECATED_BEFORE n'est VOLONTAIREMENT pas posé : il retirerait des API que
# ce code n'a jamais pu essayer de compiler, et l'échec se découvrirait en intégration
# continue sans que personne ici ne puisse l'anticiper. Ce durcissement appartient au lot
# qui disposera d'une compilation réelle.
target_compile_definitions(acp_core PUBLIC
    QT_NO_CAST_FROM_ASCII
    QT_NO_CAST_TO_ASCII
    QT_NO_URL_CAST_FROM_STRING
    QT_NO_FOREACH
)

if(MSVC)
    target_compile_options(acp_core PUBLIC /W4 /permissive- /utf-8 /Zc:__cplusplus)
else()
    target_compile_options(acp_core PUBLIC -Wall -Wextra -Wpedantic)
endif()

# --- Modules QML --------------------------------------------------------------
#
# L'exécutable n'existe pas encore : cette amorce livre le système de construction, la
# chaîne des jetons de design, la coquille QML et la logique de présentation. Le client
# authentifié et le flux d'événements viennent ensuite, avec le point d'entrée.

add_subdirectory(qml)

# --- Tests --------------------------------------------------------------------

if(ACP_DESKTOP_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
