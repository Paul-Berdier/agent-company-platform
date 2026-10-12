// Coffre ACP : client propriétaire de Hermes ; aucun accès direct au disque du bridge.
#pragma once
#include "models/JsonListModel.h"
#include "viewmodels/PageViewModel.h"
#include <QDateTime>
#include <QHash>
#include <QJsonObject>
#include <QPointer>
#include <QTimer>
#include <functional>

namespace acp {
class ApiCall;
class ClientGreffonPoste;
class ObsidianViewModel : public PageViewModel
{
    Q_OBJECT
    Q_PROPERTY(JsonListModel *notes READ notes CONSTANT)
    Q_PROPERTY(JsonListModel *backlinks READ backlinks CONSTANT)
    Q_PROPERTY(QVariantMap graphe READ graphe NOTIFY grapheChange)
    Q_PROPERTY(QVariantMap coffre READ coffre NOTIFY etatChange)
    Q_PROPERTY(QString etat READ etat NOTIFY etatChange)
    Q_PROPERTY(QString etatLibelle READ etatLibelle NOTIFY etatChange)
    Q_PROPERTY(QString erreur READ erreur NOTIFY etatChange)
    Q_PROPERTY(QString lecture READ lecture NOTIFY etatChange)
    Q_PROPERTY(bool occupe READ occupe NOTIFY etatChange)
    Q_PROPERTY(QString operation READ operation NOTIFY etatChange)
    Q_PROPERTY(QString recherche READ recherche WRITE setRecherche NOTIFY rechercheChange)
    Q_PROPERTY(QString chemin READ chemin NOTIFY noteChange)
    Q_PROPERTY(QString brouillon READ brouillon WRITE setBrouillon NOTIFY noteChange)
    Q_PROPERTY(bool noteOuverte READ noteOuverte NOTIFY noteChange)
    Q_PROPERTY(bool noteLue READ noteLue NOTIFY noteChange)
    Q_PROPERTY(bool modifie READ modifie NOTIFY noteChange)
    Q_PROPERTY(bool nouvelle READ nouvelle NOTIFY noteChange)
    Q_PROPERTY(bool conflit READ conflit NOTIFY noteChange)
    Q_PROPERTY(QString versionServeur READ versionServeur NOTIFY noteChange)
    Q_PROPERTY(bool versionServeurDisponible READ versionServeurDisponible NOTIFY noteChange)
    Q_PROPERTY(QString codeEnrolement READ codeEnrolement NOTIFY codeChange)
    Q_PROPERTY(int codeSecondes READ codeSecondes NOTIFY codeChange)
    Q_PROPERTY(bool tronque READ tronque NOTIFY etatChange)
public:
    ObsidianViewModel(ClientGreffonPoste *, EventStreamService *, QObject *parent = nullptr);
    ~ObsidianViewModel() override;
    JsonListModel *notes() const { return m_notes; }
    JsonListModel *backlinks() const { return m_backlinks; }
    QVariantMap graphe() const { return m_graphe.toVariantMap(); }
    QVariantMap coffre() const { return m_coffre.toVariantMap(); }
    QString etat() const { return m_etat; }
    QString etatLibelle() const;
    QString erreur() const { return m_erreur; }
    QString lecture() const;
    bool occupe() const { return m_appel || !m_operationId.isEmpty(); }
    QString operation() const { return m_operationEtat; }
    QString recherche() const { return m_recherche; }
    void setRecherche(const QString &);
    QString chemin() const { return m_selection; }
    QString brouillon() const;
    void setBrouillon(const QString &);
    bool noteOuverte() const { return !m_selection.isEmpty(); }
    bool noteLue() const;
    bool modifie() const;
    bool nouvelle() const;
    bool conflit() const;
    QString versionServeur() const;
    bool versionServeurDisponible() const;
    QString codeEnrolement() const { return m_code; }
    int codeSecondes() const;
    bool tronque() const { return m_tronque; }
    void setPressePapier(std::function<bool(const QString &)> presse) { m_presse = std::move(presse); }
    Q_INVOKABLE void actualiser();
    Q_INVOKABLE void fermerSuivi(bool confirmation);
    Q_INVOKABLE void lister();
    Q_INVOKABLE void chercher();
    Q_INVOKABLE void ouvrirNote(const QString &);
    Q_INVOKABLE void nouvelleNote(const QString &);
    Q_INVOKABLE void relire();
    Q_INVOKABLE void sauvegarder();
    Q_INVOKABLE void archiver(bool confirmation);
    Q_INVOKABLE void renommer(const QString &destination, bool confirmation);
    Q_INVOKABLE void lireBacklinks();
    Q_INVOKABLE void lireGraphe();
    Q_INVOKABLE void utiliserVersionServeur(bool confirmation);
    Q_INVOKABLE void garderBrouillonSurVersionServeur(bool confirmation);
    Q_INVOKABLE void creerCode();
    Q_INVOKABLE bool copierCode();
    Q_INVOKABLE void confirmerEmpreinte(const QString &empreinteSaisie);
    Q_INVOKABLE void revoquer(bool confirmation);
    Q_INVOKABLE bool capacite(const QString &action) const;
    static bool cheminValide(const QString &);
    static bool empreinteValide(const QString &);
signals:
    void etatChange();
    void noteChange();
    void rechercheChange();
    void grapheChange();
    void codeChange();
protected:
    void surActivite(bool) override;
    void surLienRetabli() override;
    void surOubli() override;
private:
    struct Note { QString texte, origine, empreinte, distant, empreinteDistante; bool neuve=false, conflit=false; };
    void adopterStatut(const QJsonObject &);
    void appeler(ApiCall *, std::function<void(const QJsonObject &)>, bool suivi = false, bool lectureStatut = false, bool creationOperation = false);
    void lancer(const QString &, const QJsonObject &);
    void sonderOperation();
    void adopterOperation(const QJsonObject &);
    bool appliquerResultat(const QJsonObject &);
    void effacerCode();
    void viderNotes();
    ClientGreffonPoste *m_greffon;
    JsonListModel *m_notes;
    JsonListModel *m_backlinks;
    QPointer<ApiCall> m_appel;
    QTimer m_suivi, m_presence, m_horlogeCode;
    quint64 m_generation = 0;
    QJsonObject m_coffre, m_graphe, m_parametres;
    QHash<QString, Note> m_brouillons;
    QString m_etat = QStringLiteral("inconnu"), m_erreur, m_recherche, m_selection;
    QString m_operationId, m_action, m_operationEtat, m_coffreOperation;
    QString m_code;
    qint64 m_codeExpire = 0;
    QDateTime m_luA;
    bool m_tronque = false;
    std::function<bool(const QString &)> m_presse;
};
}
