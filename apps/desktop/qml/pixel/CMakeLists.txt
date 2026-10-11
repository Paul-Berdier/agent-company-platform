# Acp.Pixel — direction artistique Pixel Atelier (D165) : planches et composants pixel.
#
# Les PNG et le singleton PlanchesPixel.qml sont ENGENDRÉS par scripts/generer_assets_pixel.py
# depuis design/pixel ; ils ne se modifient jamais à la main (--check en CI).

acp_mark_qml_singletons(PlanchesPixel.qml)

acp_add_qml_module(
    TARGET acp_pixel
    URI Acp.Pixel
    QML_FILES
        PlanchesPixel.qml
        FondPixel.qml
        SpritePixel.qml
        PortraitAgent.qml
        TextePixel.qml
        Embleme.qml
        PictoProjet.qml
    RESOURCES
        assets/embleme-16.png
        assets/embleme-20.png
        assets/embleme-24.png
        assets/embleme-32.png
        assets/embleme-40.png
        assets/embleme-48.png
        assets/embleme-64.png
        assets/embleme-128.png
        assets/embleme-256.png
        assets/portraits.png
        assets/police.png
        assets/pictogrammes.png
)
