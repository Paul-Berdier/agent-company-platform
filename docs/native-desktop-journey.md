# Parcours natif contre l’API locale

Le test `tst_api_journey` exerce les vrais transports et modèles Qt contre
`acp_api.main:app`, sur les sources du worktree courant. Il reste ignoré par la
suite CTest ordinaire lorsque `ACP_DESKTOP_TEST_API_URL` est absent.

Après compilation de la cible, lancer depuis la racine du worktree :

```powershell
python scripts/verify-desktop-journey.py --qt-bin C:/Qt/6.8.3/msvc2022_64/bin
```

Utiliser le Python de l’environnement API et le chemin du SDK Qt effectivement
installé. `--qt-test <binaire>` permet de choisir un autre répertoire de build.
Le lanceur ne compile rien et n’installe aucune dépendance.

À chaque exécution, un nouveau dossier `.test-tmp/desktop-journey-<uuid>` contient
SQLite, les stockages, le marqueur du décor et les preuves. Aucune base existante
n’est ouverte. Le lanceur écarte les variables ACP héritées, démarre une API sur
le bouclage local, puis vérifie son marqueur HTTP avant le bootstrap. Ce marqueur
est ajouté uniquement par le processus de test ; les routes métier ne sont pas
remplacées. Les secrets jetables voyagent dans l’environnement des processus et
ne sont pas écrits dans le rapport.

Le décor est créé par les API de bootstrap, organisation, espace, projet et
mission. Un worker hors ligne et un livrable synthétique sont ensuite insérés
dans cette seule base, à titre de fixture. Le stockage réel écrit le blob ; le
test télécharge ensuite ce contenu par l’endpoint protégé habituel.

Le parcours Qt vérifie :

- connexion par cookie et CSRF, création et lecture des organisations, espaces et projets ;
- création d’une conversation et conservation explicite du message lorsque Hermes est indisponible ;
- création, liste et détail d’une mission, dont la tentative reste réellement en attente ;
- consommation inconnue conservée, modification des limites budgétaires et création d’une automation en pause ;
- liste, métadonnées et export atomique d’un livrable, avec comparaison de la taille et du SHA-256 ;
- purge des données locales à la déconnexion.

Les API de projet ne proposent pas ici de modification ou de suppression : ce
parcours couvre la création et la lecture. Il ne valide pas un fournisseur IA,
un worker exécutant une mission, le rendu QML ni les dialogues natifs.

`--seed-only` vérifie uniquement le démarrage et le décor API. Son résultat est
`seed_ready_only`, jamais `passed`. Un parcours Qt n’est déclaré `passed` que si
le processus termine à zéro et si son rapport JUnit contient `realApiJourney`
sans échec ni saut. `result.json`, `qt-journey.log`, `qt-journey.xml` et `api.log`
restent dans le dossier jetable pour inspection ; l’API est arrêtée en fin de run.

Après compilation du shell de test `desktop_preview`, `--interactive-shell`
ouvre une session native sur un nouveau décor pendant dix minutes au maximum.
`--shell-exe` permet d’indiquer son chemin. L’API reste vivante jusqu’à la fermeture
du shell ou l’expiration du délai. Ce mode écrit `preview_closed`, `preview_failed`
ou `preview_timeout`, jamais `passed` ; fermer la fenêtre ne prouve pas une recette.
Il conserve son journal dans `desktop-preview.log` et n’exécute pas le QtTest.

Le workflow `desktop-ci.yml` lance également le parcours après CTest, avec
Python 3.12 et un environnement isolé. Il prépare les dépendances Windows avec
`scripts/prepare-desktop-python-lock.py`, puis conserve seulement les quatre
preuves `qt-journey.log`, `qt-journey.xml`, `result.json` et `api.log`, sans publier
la base du décor. L’existence de cette étape ne constitue pas une preuve de CI
verte : consulter le résultat effectif du run correspondant au commit.
