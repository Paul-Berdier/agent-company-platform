# Studio en direct : tests et navigateur

Date d'état : 11 septembre 2026
Statut : architecture cible du lot E ; module non livré

## Objectif

Le Studio doit montrer la session qui exécute réellement une mission web : contexte
Playwright, onglet, étapes, assertions, logs et preuves. Ouvrir la même URL dans un
autre navigateur ne constitue pas une observation du test. Une navigation sans
assertion ne devient jamais un test réussi.

Au 11 septembre 2026, le nouveau shell a été parcouru dans un navigateur intégré et
deux captures de son rendu sont conservées dans `docs/assets/screenshots`. Ce test
de l'interface plateforme n'est pas le Studio : aucun navigateur de mission,
reporter Playwright ou flux de test n'est raccordé.

## Architecture cible

```text
Runner isolé
  ├── Playwright + reporter ACP
  ├── contexte/onglet réellement exécuté
  ├── images de session à cadence bornée
  └── trace, vidéo, captures, console et réseau
            │
            ▼
Ingestion authentifiée ── événements durables + stockage d'objets privé
            │
            ├── flux temps réel borné
            └── manifeste de replay immuable
                         │
                         ▼
              Studio web / lien depuis le CLI
```

Le reporter émet des événements structurés : suite, test, étape, assertion, statut,
durée, tentative, pièces jointes et références d'artefacts. Les statuts `skipped`,
`flaky`, `timed_out` et `interrupted` restent distincts.

Les images et vidéos ne transitent pas en base64 dans le journal d'événements. Le
journal contient une référence authentifiée vers le stockage privé, une empreinte,
le type MIME, la taille et la provenance.

## Modes affichés

| Libellé | Condition réelle |
|---|---|
| **Direct** | image provenant du contexte actif, flux connecté, horodatage récent |
| **Aperçu intermédiaire** | dernière image produite pendant un calcul ou un flux momentanément indisponible |
| **Replay** | lecture d'artefacts clôturés avec chronologie et manifeste persistés |
| **Hors ligne / inconnu** | aucune preuve fraîche ; aucune interpolation d'état |

L'interface affiche toujours le contexte, l'onglet ou le test sélectionné, la date
de la dernière image et l'état de connexion. Plusieurs contextes ne sont jamais
fusionnés comme s'ils formaient un même flux.

## Reprise en main humaine

Le Studio est en lecture seule par défaut. La prise de contrôle :

1. demande une approbation explicite liée au run, au navigateur et à une durée ;
2. acquiert un lease exclusif côté serveur ;
3. suspend ou interrompt l'agent uniquement si le runner confirme cette capacité ;
4. journalise l'acteur, l'heure et les actions de contrôle ;
5. marque le test automatisé comme perturbé lorsqu'une action humaine modifie son
   contexte ;
6. rend le contrôle à l'agent par une action explicite et une nouvelle
   réconciliation.

Perdre le flux ou fermer le Studio n'arrête pas le run. L'arrêt reste une commande
distincte.

## Menaces et contrôles requis

| Menace | Contrôle requis |
|---|---|
| Aperçu hostile avec cookies de la plateforme | origine dédiée, profil navigateur sans session ACP, CSP stricte, isolation du contenu et aucune clé plateforme injectée |
| HTML, SVG ou trace active | rendu sandboxé, téléchargement avec type sûr, nettoyage lorsque possible ; jamais dans l'origine privilégiée |
| Lecture d'un flux d'un autre projet | autorisation serveur sur chaque abonnement, événement et URL d'artefact |
| URL de média partagée ou durable | URL signée courte, audience et objet bornés, révocation ; aucun projet rendu public |
| Port ou tunnel arbitraire | registre de ports du runner, allowlist par run, authentification et expiration du tunnel |
| Traversée de chemins | identifiants opaques, racine de run imposée, résolution canonique et rejet des liens |
| Fuite de secrets dans l'écran | comptes de test par défaut, capture désactivable, pause lors d'une saisie privée ; avertissement qu'un filtre de logs ne masque pas les pixels |
| Prise de contrôle concurrente | lease exclusif, expiration, fencing token et réconciliation avec le runner |
| Saturation réseau ou stockage | cadence et qualité adaptatives, quotas, rétention, backpressure et arrêt des captures inutiles |
| Faux succès | succès dérivé des assertions et codes de sortie, jamais d'une image ou d'un résumé LLM |

## Critères d'acceptation du lot E

- Un test Playwright réel produit des événements structurés associés au bon run et
  au bon projet.
- Le Studio affiche le contexte utilisé, les étapes et une image horodatée de cette
  session, pas un navigateur parallèle.
- Un échec conserve capture, trace et, selon la politique, vidéo ; ces artefacts
  sont consultables après redémarrage des services.
- Une reconnexion par curseur ne double ni les étapes ni le lancement du test.
- `skipped`, `flaky`, `timed_out` et `interrupted` sont rendus sans être convertis en
  réussite ou en échec générique.
- Un lecteur autorisé peut observer mais pas contrôler ; un utilisateur d'un autre
  projet ne peut lire ni flux ni artefact.
- La prise de contrôle est exclusive, suspend l'automate lorsque cette capacité est
  réelle et distingue le résultat perturbé.
- Les URLs signées expirent ; un replay reste accessible via une nouvelle
  autorisation sans rendre le fichier public.
- Les limites de cadence, bande passante, volume et rétention sont testées.

Ces critères couvrent principalement les scénarios d'acceptation 10, 11, 12 et 19.
Aucun n'est satisfait de bout en bout.

## État réel

### Réalisé/vérifié

- Les responsabilités et frontières de sécurité du Studio sont documentées.
- La suite du moteur pixel reste verte (117 tests), mais elle ne constitue aucune
  preuve du Studio et le pixel art reste une fonction legacy.

### Réalisé, non testé réel

- Le shell moderne réserve les parcours de suivi et présente les fonctionnalités
  non raccordées comme telles. Son rendu a été capturé, mais aucun test Playwright
  de mission ou flux Studio réel ne l'a encore alimenté.

### Non configuré

- Playwright sur un runner ;
- reporter ACP et ingestion structurée ;
- stockage d'objets privé ;
- flux d'images, trace viewer et replay ;
- origine d'aperçu, tunnel et comptes de test ;
- contrôle humain exclusif et politique de rétention.

### Restant

- implémenter le reporter, le protocole d'événements et les artefacts ;
- raccorder un premier runner web isolé ;
- créer le Studio et le lien `acp open --run` ;
- exécuter les tests fonctionnels, sécurité et charge décrits ci-dessus ;
- produire et vérifier les captures de la session de test réellement exécutée.
