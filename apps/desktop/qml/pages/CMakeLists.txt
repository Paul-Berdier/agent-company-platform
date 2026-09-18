# Acp.Pages — écrans livrés par cette fondation.
#
# Trois seulement : première ouverture, accueil, diagnostics. Les autres destinations sont
# déclarées par NavigationModel comme « prévues » et n'ont volontairement aucun fichier
# ici : une coquille vide serait un faux succès.

acp_add_qml_module(
    TARGET acp_pages
    URI Acp.Pages
    QML_FILES
        DiagnosticsPage.qml
        FirstRunPage.qml
        HomePage.qml
)
