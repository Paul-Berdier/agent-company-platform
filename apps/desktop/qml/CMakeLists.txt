# Modules QML de la station.
#
# Un module par répertoire, un URI par module. Chaque `import` d'un fichier QML désigne
# donc exactement un répertoire du dépôt.
#
# Ordre voulu : les modules sans dépendance d'abord. Ce n'est pas une contrainte de CMake
# — les modules QML se résolvent à l'exécution — mais cela rend le graphe lisible.

add_subdirectory(theme)
add_subdirectory(controls)
add_subdirectory(components)
add_subdirectory(pages)
add_subdirectory(shell)

# Module racine : il ne contient que App.qml. Le nom de cible diffère de celui de
# l'exécutable (acp_desktop) parce que l'exécutable n'est pas la cible d'appui du module :
# App.qml doit se trouver à la RACINE de son module pour que loadFromModule("Acp.Desktop",
# "App") le trouve, ce qui impose un module enraciné dans ce répertoire.
acp_add_qml_module(
    TARGET acp_desktop_qml
    URI Acp.Desktop
    QML_FILES App.qml
)
