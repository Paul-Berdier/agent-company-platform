# Catalogue de compétences ACP — applications au poste

Le verrou `catalogue.lock.json` distingue les sources intégrales épinglées, leur licence,
l’enveloppe de cadrage Hermes (`SKILL.md`) et l’application ACP en français (`POSTE.md`).
Les applications sont des adaptations courtes et identifiées, pas la reproduction intégrale
ni l’exécution des plugins Addy ou Ponytail. Aucun installateur, hook ou script amont n’est livré.

## Utilisation réelle

1. Mettre à jour l’image **serveur Hermes ACP** contenant ce verrou et le greffon ; une mise à jour
   du client desktop seule ne change pas les consignes du serveur. Aucun accès à un compte personnel
   n’est ajouté. Le poste ou l’exécutant autorisé doit déjà avoir publié son dépôt et ses assistants.
2. Choisir le profil du projet : `web`, `donnees` ou `recherche`. La liste `skills_poste` du profil
   indique les applications disponibles ; `base` n’ajoute aucun texte tiers implicitement.
3. Pour les **nouveaux tours et corrections composés après cette mise à jour**, le graphe sélectionne
   les applications par classe et rôle, vérifie les empreintes, puis les joint à la consigne Codex
   ou Claude et au corps de la carte. Les cartes déjà réservées conservent leur consigne d’origine.
   Aucun téléchargement ni installation de skill sur le poste n’est nécessaire.
4. Consulter la carte et les résultats de son exécution. La présence du texte au catalogue ou dans
   la consigne prouve sa disponibilité ou son injection ; elle ne prouve pas que le modèle l’a suivi,
   qu’un test a réussi ou qu’une livraison a été autorisée.

| Profil | Classe/rôle | Applications ajoutées |
|---|---|---|
| web, donnees | architecture ou documentation / implémentation ou correction | planning-and-task-breakdown |
| web, donnees | implementation / implémentation ou correction | incremental-implementation, addy-test-driven-development, ponytail |
| web | implementation / implémentation ou correction | frontend-ui-engineering en plus |
| web, donnees | petite_tache / implémentation ou correction | incremental-implementation, ponytail |
| web, donnees | debogage_tests / implémentation ou correction | addy-test-driven-development, debugging-and-error-recovery, ponytail |
| web, donnees, recherche | relecture / relecture | code-review-and-quality, ponytail-review, ponytail-audit |
| recherche | architecture ou documentation / implémentation ou correction | planning-and-task-breakdown |

Ces applications ne sont ajoutées qu’aux voies `poste-codex` et `poste-claude`. Les cartes Hermes,
l’exploration initiale et l’intégration déterministe ne reçoivent pas ce bloc. Les trois textes de
relecture imposent la lecture seule. Le nom `addy-test-driven-development` évite la collision avec
la compétence `test-driven-development` déjà fournie par Hermes.

Un catalogue invalide, une application absente ou modifiée, un chemin sortant du catalogue ou une
consigne trop longue refuse le plan avec le code `competences_poste`. Cet injecteur ne tronque
pas la mission pour faire tenir les compétences. Le protocole machine conserve ses bornes globales
et sa mention explicite de troncature si les réponses ou résumés rendent la carte trop volumineuse. Aucun réglage du volume n’est lu par cet injecteur.
Le propriétaire change ces associations par une modification du verrou relue et livrée avec l’image,
non par un bouton d’activation qui prétendrait avoir configuré un service externe.

## Chef de projet

`acp-boucle-chef` est une compétence ACP maison chargée par les cartes de planification et de
synthèse. Elle utilise les outils du projet existants et leurs limites réelles : déléguer, lire
les résultats et relectures, reprendre un défaut concret dans les plafonds, puis conclure ou
laisser la décision au propriétaire. Elle ne crée aucun nouveau planificateur, budget monétaire
ni boucle Ponytail autonome. Les plafonds de tours/cartes/corrections restent imposés par le greffon.

## Provenance et vérification

- Addy Osmani `agent-skills`, tag `0.6.12`, commit `a06bc63b3f8b829c14b0bbf53d99fefc39d58092`, MIT.
- DietrichGebert `ponytail`, commit `9b58c1ffb790c075ca32e70a89cf1d80588f4abf`, MIT.
- `hermes/THIRD_PARTY.md` reprend les licences. Chaque catégorie livre `LICENSE` et `PROVENANCE.md`.
- Les sources complètes sont renommées `SOURCE.md` pour éviter un second index de skill Hermes.
  Leurs références Markdown relatives sont conservées sous `references/amont`.
- `python scripts/verifier_catalogue.py` vérifie chemins, empreintes, références et associations ;
  `--amont` compare les octets aux commits épinglés. Les adaptations ACP sont explicitement distinctes.

La garde d’exécution Hermes et la table de routage du propriétaire restent applicables. Un texte de
compétence ne donne aucun droit supplémentaire et ne permet aucun repli caché vers un autre compte.
