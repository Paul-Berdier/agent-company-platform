#pragma once
#include <QObject>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QPointer>
#include <QStringList>
#include <QUrl>

#include <functional>
#include <optional>

class QNetworkReply;
class QSaveFile;
class QCryptographicHash;
class QTimer;
namespace acp {
class SettingsStore;
// Client GitHub séparé : aucun cookie ACP ni identifiant du serveur ne le traverse.
//
// Mise à jour automatique (D170, demande du propriétaire) : vérification au démarrage puis
// toutes les six heures, téléchargement de l'installeur joint à la publication GitHub, contrôle
// de sa taille et de son empreinte SHA-256 (SHA256SUMS.txt de la même publication), puis
// installation silencieuse au prochain démarrage, ou tout de suite à la demande, et relance.
// Échec fermé à chaque étape : un fichier dont l'empreinte diffère n'est jamais lancé.
class UpdateService : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString currentVersion READ currentVersion CONSTANT)
    Q_PROPERTY(QString latestVersion READ latestVersion NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QString notes READ notes NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool updateAvailable READ updateAvailable NOTIFY changed)
    Q_PROPERTY(bool includePrereleases READ includePrereleases WRITE setIncludePrereleases NOTIFY changed)
    Q_PROPERTY(bool autoInstall READ autoInstall WRITE setAutoInstall NOTIFY changed)
    Q_PROPERTY(bool installationPossible READ installationPossible CONSTANT)
    Q_PROPERTY(bool downloading READ downloading NOTIFY changed)
    Q_PROPERTY(int progress READ progress NOTIFY changed)
    Q_PROPERTY(bool readyToInstall READ readyToInstall NOTIFY changed)
    Q_PROPERTY(QString pendingVersion READ pendingVersion NOTIFY changed)
    Q_PROPERTY(bool installerAvailable READ installerAvailable NOTIFY changed)
public:
    //! Origines admises. Production par défaut ; les tests visent un faux GitHub de bouclage.
    struct Sources {
        QUrl api = QUrl(QStringLiteral("https://api.github.com/repos/Paul-Berdier/agent-company-platform"));
        //! Page du dépôt : préfixe exact des pages de publication et des téléchargements.
        QString depot = QStringLiteral("https://github.com/Paul-Berdier/agent-company-platform");
        //! Hôtes admis pour un téléchargement et ses redirections (HTTPS seulement en production).
        QStringList hotes = {QStringLiteral("github.com"), QStringLiteral("objects.githubusercontent.com"),
                             QStringLiteral("release-assets.githubusercontent.com")};
        bool httpAutorise = false;          //!< Tests seulement : HTTP de bouclage.
        QString dossier;                    //!< Vide : <données locales>/mises-a-jour.
        std::optional<bool> installationPermise; //!< Vide : Windows et installation par l'installeur.
        //! Lancement détaché de l'installeur (défaut : QProcess::startDetached).
        std::function<bool(const QString &, const QStringList &)> lanceur;
    };

    explicit UpdateService(QString version, QObject *parent = nullptr);
    UpdateService(QString version, SettingsStore *settings, Sources sources, QObject *parent = nullptr);
    ~UpdateService() override;
    QString currentVersion() const { return m_current; }
    QString latestVersion() const { return m_latest; }
    QString status() const { return m_status; }
    QString notes() const { return m_notes; }
    bool busy() const { return !m_reply.isNull() && !m_downloading; }
    bool updateAvailable() const { return m_available; }
    bool includePrereleases() const { return m_prereleases; }
    void setIncludePrereleases(bool enabled);
    bool autoInstall() const;
    void setAutoInstall(bool enabled);
    bool installationPossible() const;
    bool downloading() const { return m_downloading; }
    int progress() const { return m_progress; }
    bool readyToInstall() const { return m_ready; }
    QString pendingVersion() const { return m_pendingVersion; }
    //! La publication retenue joint un installeur et SHA256SUMS.txt admissibles.
    bool installerAvailable() const { return m_available && !m_installerUrl.isEmpty() && !m_sumsUrl.isEmpty(); }
    QString dossierTelechargements() const;

    Q_INVOKABLE void check();
    Q_INVOKABLE void openRelease();
    //! Télécharge la version publiée puis l'installe aussitôt (la station redémarre).
    Q_INVOKABLE void downloadAndInstall();
    //! Installe la version déjà téléchargée et vérifiée (la station redémarre).
    Q_INVOKABLE void installNow();

    //! Vérifications automatiques : 30 secondes après le démarrage, puis toutes les six heures,
    //! seulement si l'installation automatique est active.
    void startAutomaticChecks();
    //! Au démarrage, avant toute fenêtre : installe une version téléchargée et vérifiée lors d'une
    //! session précédente. Vrai si l'installeur a été lancé (la station doit alors s'arrêter).
    bool installPendingAtStartup();

    // Politique pure, partagée par le transport et les tests de données non fiables.
    static int compareVersions(const QString &left, const QString &right, bool *valid);
    static bool validateRelease(const QJsonObject &release, bool prereleases);
    static bool validateRelease(const QJsonObject &release, bool prereleases, const QString &depot);
    //! Empreinte d'un fichier dans un SHA256SUMS.txt (« <64 hex>  <nom> »), en minuscules ; vide si absente.
    static QString empreinteDans(const QByteArray &sommes, const QString &nom);
    static QStringList argumentsInstalleur();
signals:
    void changed();
    //! Une version est téléchargée et vérifiée : elle s'installera au prochain démarrage.
    void updateReady(const QString &version);
    //! L'installeur est lancé : la station doit s'arrêter pour le laisser remplacer ses fichiers.
    void quitRequested();
    //! L'installeur lancé pour cette version n'a pas mis la station à jour.
    void installationFailed(const QString &version);
private:
    void fail(const QString &reason);
    void accept(const QByteArray &body);
    void download(bool installAfter);
    void downloadInstaller();
    void finishDownload();
    void abandonDownload(const QString &reason);
    void clearPending();
    bool urlAdmise(const QUrl &url) const;
    QNetworkReply *get(const QUrl &url, const QByteArray &accept, int transferTimeoutMs);
    QString cheminEtat() const;
    QJsonObject lireEtat() const;
    bool ecrireEtat(const QJsonObject &etat) const;
    static QString empreinteFichier(const QString &chemin);

    SettingsStore *m_settings = nullptr;
    Sources m_sources;
    QNetworkAccessManager m_network;
    QPointer<QNetworkReply> m_reply;
    QString m_current, m_latest, m_notes;
    QString m_status = QStringLiteral("Aucune vérification effectuée. GitHub sera contacté à votre demande.");
    QUrl m_releaseUrl;
    bool m_available = false;
    bool m_prereleases = false;
    bool m_autoInstallMemoire = true;
    // Installeur de la publication retenue.
    QUrl m_installerUrl, m_sumsUrl;
    QString m_installerName, m_installerDigest;
    qint64 m_installerSize = -1;
    // Téléchargement en cours.
    bool m_downloading = false;
    bool m_installAfter = false;
    int m_progress = 0;
    QString m_expectedSha256;
    qint64 m_received = 0;
    QSaveFile *m_file = nullptr;
    QCryptographicHash *m_hash = nullptr;
    // Version prête à installer.
    bool m_ready = false;
    QString m_pendingVersion, m_pendingFile, m_pendingSha256;
    QTimer *m_timer = nullptr;
};
}
