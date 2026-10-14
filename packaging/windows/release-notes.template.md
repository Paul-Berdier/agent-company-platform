# Agent Company Platform {{VERSION}} — Workspace Hermes et coffre ACP pour Windows

Client natif C++23 / Qt 6 / QML, connecté au Hermes du propriétaire par son
fournisseur d’identité et le navigateur système.

## Nouveautés

- **Discussion** : recherche et chargement progressif jusqu’à 500 discussions,
  renommage, copie avec historique, choix du modèle pour la session, Markdown
  contrôlé et copie du code. Le modèle effectif et le contexte sont affichés quand
  Hermes les communique. Les brouillons restent en mémoire pendant la navigation ;
  un envoi refusé ou non confirmé est conservé sans renvoi automatique.
- **Coffre ACP** : notes Markdown locales, recherche, édition avec contrôle de
  version, création, renommage, archives récupérables, liens entrants et graphe.
  Le lanceur **Coffre ACP - Obsidian** et son runtime sont inclus. Aucune installation
  de Python ni extension Obsidian n’est nécessaire. L’association à Hermes reste
  volontaire ; l’identité du pont est distincte de celle de l’exécutant.
- **Outils** : catalogue réel du serveur et dix fiches sourcées, provenance et
  préparation d’une consigne sans envoi. Six méthodes Addy et trois méthodes
  Ponytail, épinglées sous licence MIT, sont adaptées aux tâches des assistants
  après mise à jour du serveur et sélection du profil approprié. Aucun programme
  ni hook de ces dépôts n’est installé.

Guide complet : [workspace, coffre et mise à jour 1.2.0](https://github.com/Paul-Berdier/agent-company-platform/blob/v{{VERSION}}/docs/refonte/workspace-1.2.0.md).

## Fichiers et signature

| Fichier | Usage |
|---|---|
| `{{PREFIXE}}-Setup-{{VERSION}}-{{SUFFIXE}}.exe` | Installation ou mise à jour par utilisateur |
| `{{PREFIXE}}-Portable-{{VERSION}}-{{SUFFIXE}}.zip` | Extraire dans un nouveau dossier, puis lancer `AgentCompanyPlatform.exe` |
| `SHA256SUMS.txt` | Empreintes des deux paquets |

{{SIGNATURE}}

Comparez l’empreinte du paquet à sa ligne dans `SHA256SUMS.txt` avant de l’exécuter :

```powershell
Get-FileHash .\{{PREFIXE}}-Setup-{{VERSION}}-{{SUFFIXE}}.exe -Algorithm SHA256
```

Les paquets CI utilisent le décor ACP original. Un paquet local intégrant les
ressources LimeZu sous licence est distinct, avec ses propres empreintes ; les
sources LimeZu ne sont pas publiées dans Git ni jointes séparément à la release.

## Installer ou mettre à jour

1. Sauvegardez hors d’ACP les brouillons utiles de Discussion et du coffre. Fermez
   ACP et la fenêtre du pont si elle est ouverte.
2. Lancez le nouveau Setup avec le **même compte Windows**, sans désinstaller
   l’ancienne version. Pour le portable, utilisez un nouveau dossier sans mélanger
   les DLL de deux versions.
3. Rouvrez ACP, conservez l’URL Hermes habituelle et vérifiez **{{VERSION}}** dans
   **Réglages → Mises à jour**. Reconnectez-vous par le navigateur si la session le
   demande. Les préférences et la session mémorisée avec consentement restent dans
   le profil Windows et son coffre ; les projets restent sur Hermes.
4. Pour le coffre et les nouvelles compétences, vérifiez que le serveur annonce
   aussi le **greffon ACP 1.2.0**. Le Setup ne met à jour ni Hermes ni l’exécutant
   Railway. L’application n’installe pas automatiquement les mises à jour ; son
   bouton de mise à jour ne voit pas les releases encore en brouillon.
5. Une fois Hermes à jour, ouvrez **Coffre ACP** pour générer le code d’association,
   puis **Coffre ACP - Obsidian → Associer ce coffre à Hermes**. Comparez et confirmez
   l’empreinte dans ACP. Démarrez le bridge et laissez sa fenêtre ouverte. Si votre
   dossier `Documents/ACP-notes` existe déjà, conservez-le : ne recréez pas le coffre.

Un service Railway épinglé par `source.commitSha` ne suit pas les nouvelles fusions :
son déploiement demande un geste du propriétaire. Vérifiez la configuration réelle
des services avant de déduire qu’une fusion les a mis à jour. Sans cette épingle,
une fusion peut déclencher une reconstruction selon les chemins surveillés.

**Avant la transition serveur**, appliquez le [manuel, § 6.4 et § 6.5](https://github.com/Paul-Berdier/agent-company-platform/blob/v{{VERSION}}/docs/exploitation.md#64-vos-gestes-et-le-point-de-non-retour) :
pause générale, aucune carte en main, sauvegarde d’`executant-donnees` puis de
`hermes-donnees`, et export chiffré. Conservez les volumes, les secrets et les
identités existantes. Le lot ajoute trois tables du coffre et un index sans modifier
les anciennes tables ; l’épingle amont de Hermes reste inchangée. Après déploiement,
contrôlez le commit réellement démarré, le greffon 1.2.0 et la compatibilité avant
reprise. La préparation des sauvegardes précède toute transition serveur, même si
le client desktop a déjà été installé.

## Portée et limites

Les neuf actions du coffre sont déclenchées par le propriétaire dans le desktop.
**Aucun outil de lecture ou d’écriture du coffre n’est exposé aux agents Hermes
ni à Discussion dans cette version.** Les notes demandées transitent par Hermes ;
ses sauvegardes peuvent garder des copies après la purge applicative. Les notes
sont limitées à 128 Kio. Renommer ne réécrit pas les autres liens ; Bases, Canvas et
l’ensemble des extensions Obsidian ne sont pas interprétés.

Les versions remplacées et notes archivées restent dans `.acp/archives`. Ne
supprimez pas `.acp/operations`, qui évite de répéter une mutation interrompue.
Après purge d’une ancienne opération sur le serveur, le pont peut conserver son
résultat sous `%LOCALAPPDATA%/ACP/coffre-notes/resultats-non-acquittes`, sans rejouer
l’écriture. Ce résultat reste **non acquitté** : relisez la note avant de la modifier.
La récupération et ses bornes sont décrites dans le guide.

Les fiches CRM, REA, Douyin/TikTok, ML Intern, Hackingtool, Graphify et OmniRoute ne
signifient pas que ces services sont installés ou connectés. ML Intern est archivé.
Aucun compte personnel n’a été connecté par les tests. Le terminal web, les pièces
jointes et la parité complète avec Hermes web restent hors de ce lot. Les brouillons
ne survivent pas à la fermeture ou à la perte de session.

Les validations isolées utilisent notamment un faux Hermes et des coffres jetables ;
elles ne prouvent ni la session personnelle, ni l’installation sur le PC du
destinataire. Ces notes n’attestent pas la réussite du workflow Desktop Release ni
l’exécution de ses paquets. Le relevé des validations sera lié depuis ces notes
après fusion de la PR de preuves dans `main`.
