# Cibles de test de la station.
#
# Exécutés par scripts/test-desktop.ps1 (ctest) sur poste et dans desktop-ci.yml.
#
# Deux familles :
#   - Qt Test (C++) : analyseur SSE, erreurs d'API, registre de commandes, machine à états
#     de session, compatibilité, curseurs, expurgation, contrôles de disponibilité. Ils
#     ne touchent pas le réseau et n'ouvrent aucune fenêtre. Ceux qui lisent un document
#     d'API le prennent dans fixtures/, que la suite Python garde aligné sur l'API réelle
#     (apps/api/tests/test_desktop_contract_fixtures.py) ;
#   - Qt Quick Test (QML) : composants de la coquille, sur une scène réelle.

find_package(Qt6 6.8 REQUIRED COMPONENTS Test QuickTest)

# --- Tests C++ ----------------------------------------------------------------

function(acp_add_cpp_test name)
    qt_add_executable(${name} cpp/${name}.cpp)
    target_link_libraries(${name} PRIVATE acp_core Qt6::Test)
    # Les tests sont des programmes de console : pas de sous-système fenêtré sur Windows,
    # sans quoi leur sortie serait invisible pour ctest.
    set_target_properties(${name} PROPERTIES WIN32_EXECUTABLE FALSE)
    add_test(NAME ${name} COMMAND ${name})
    # Les tests n'ouvrent aucune fenêtre : la plateforme « offscreen » évite qu'un runner
    # sans session graphique ne les fasse échouer pour une mauvaise raison.
    set_tests_properties(${name} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
endfunction()

acp_add_cpp_test(tst_sse_parser)
acp_add_cpp_test(tst_api_errors)
acp_add_cpp_test(tst_command_registry)
acp_add_cpp_test(tst_session_state)
target_compile_definitions(tst_session_state PRIVATE
    ACP_TEST_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/fixtures"
)
acp_add_cpp_test(tst_compatibility)
# Document /meta réel, versionné ; tests/test_desktop_meta_fixture.py (côté API) échoue si
# la forme servie par le serveur s'en écarte.
target_compile_definitions(tst_compatibility PRIVATE
    ACP_TEST_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/fixtures"
)
acp_add_cpp_test(tst_cursors)
acp_add_cpp_test(tst_redaction)
acp_add_cpp_test(tst_backoff)
acp_add_cpp_test(tst_readiness)
target_compile_definitions(tst_readiness PRIVATE
    ACP_TEST_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/fixtures"
)

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
