# Cibles de test de la station.
#
# AVERTISSEMENT : aucun de ces tests n'a jamais été compilé ni exécuté. Le poste de
# rédaction n'a ni compilateur, ni Qt, ni CMake. Ils sont écrits POUR l'intégration
# continue, qui est la seule preuve recevable.
#
# Deux familles :
#   - Qt Test (C++) : analyseur SSE, erreurs d'API, registre de commandes, machine à états
#     de session, compatibilité, curseurs, expurgation. Ils ne touchent pas le réseau et
#     n'ouvrent aucune fenêtre ;
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
acp_add_cpp_test(tst_compatibility)
acp_add_cpp_test(tst_cursors)
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
)
set_target_properties(tst_qml_shell PROPERTIES WIN32_EXECUTABLE FALSE)
add_test(NAME tst_qml_shell COMMAND tst_qml_shell)
set_tests_properties(tst_qml_shell PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
