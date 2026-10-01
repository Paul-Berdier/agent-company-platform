# Cibles de test de la station.
#
# Exécutés par scripts/test-desktop.ps1 (ctest) sur poste et dans desktop-ci.yml.
#
# Deux familles :
#   - Qt Test (C++) : analyseur SSE, erreurs d'API, registre de commandes et navigation,
#     expurgation, recul, mises à jour, chargement des pages. Ils ne visent jamais un
#     serveur réel : ceux qui parlent HTTP le font à un faux serveur de bouclage ;
#   - Qt Quick Test (QML) : composants de la coquille, sur une scène réelle.

find_package(Qt6 6.8 REQUIRED COMPONENTS Test QuickTest)

# --- Tests C++ ----------------------------------------------------------------

function(acp_add_cpp_test name)
    qt_add_executable(${name} cpp/${name}.cpp ${ARGN})
    target_link_libraries(${name} PRIVATE acp_core Qt6::Test)
    target_include_directories(${name} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/cpp")
    # Les tests sont des programmes de console : pas de sous-système fenêtré sur Windows,
    # sans quoi leur sortie serait invisible pour ctest.
    set_target_properties(${name} PROPERTIES WIN32_EXECUTABLE FALSE)
    add_test(NAME ${name} COMMAND ${name})
    # Les tests n'ouvrent aucune fenêtre : la plateforme « offscreen » évite qu'un runner
    # sans session graphique ne les fasse échouer pour une mauvaise raison.
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endfunction()

acp_add_cpp_test(tst_sse_parser)
acp_add_cpp_test(tst_updates)
acp_add_cpp_test(tst_desktop_pages)
target_link_libraries(tst_desktop_pages PRIVATE Qt6::QuickControls2
    acp_designplugin acp_themeplugin acp_controlsplugin acp_componentsplugin
    acp_pagesplugin acp_stationplugin acp_desktop_qmlplugin)
acp_add_cpp_test(tst_api_errors)
acp_add_cpp_test(tst_api_porteur cpp/support/FauxHermes.cpp cpp/support/FauxHermes.h)
acp_add_cpp_test(tst_pkce)
acp_add_cpp_test(tst_client_greffon cpp/support/FauxHermes.cpp cpp/support/FauxHermes.h)
acp_add_cpp_test(tst_flux_natif cpp/support/FauxHermes.cpp cpp/support/FauxHermes.h
    cpp/support/NavigateurTest.h)
acp_add_cpp_test(tst_session_hermes cpp/support/FauxHermes.cpp cpp/support/FauxHermes.h
    cpp/support/NavigateurTest.h cpp/support/CoffreMemoire.h)
acp_add_cpp_test(tst_jetons_coffre cpp/support/CoffreMemoire.h)
acp_add_cpp_test(tst_instance_unique)
acp_add_cpp_test(tst_compatibilite_hermes cpp/support/FauxHermes.cpp cpp/support/FauxHermes.h)
# Documents de référence du greffon (forme de meta.py, voir fixtures/hermes/README.md).
target_compile_definitions(tst_compatibilite_hermes PRIVATE
    ACP_TEST_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/fixtures"
)
acp_add_cpp_test(tst_sante cpp/support/FauxHermes.cpp cpp/support/FauxHermes.h)
acp_add_cpp_test(tst_reglages_sans_secret cpp/support/FauxHermes.cpp cpp/support/FauxHermes.h
    cpp/support/NavigateurTest.h cpp/support/CoffreMemoire.h)
acp_add_cpp_test(tst_command_registry)
acp_add_cpp_test(tst_redaction)
acp_add_cpp_test(tst_backoff)

# --- Tests QML ----------------------------------------------------------------
#
# QUICK_TEST_SOURCE_DIR indique au harnais où chercher les fichiers « tst_*.qml ».
# https://doc.qt.io/qt-6/qtquicktest-index.html — consulté le 18 septembre 2026.

qt_add_executable(tst_qml_shell qml/tst_qml_shell.cpp)
target_compile_definitions(tst_qml_shell PRIVATE
    QUICK_TEST_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/qml"
)
target_link_libraries(tst_qml_shell PRIVATE
    acp_core
    Qt6::Qml
    Qt6::Quick
    Qt6::QuickTest
    acp_designplugin
    acp_themeplugin
    acp_controlsplugin
    acp_componentsplugin
    Qt6::QuickControls2
)
set_target_properties(tst_qml_shell PROPERTIES WIN32_EXECUTABLE FALSE)
add_test(NAME tst_qml_shell COMMAND tst_qml_shell)
set_tests_properties(tst_qml_shell PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
