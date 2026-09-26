# Interface ACP — greffons du tableau de bord de Hermes

Sources TypeScript des trois greffons de tableau de bord qu'ACP livre dans son image Hermes
(étapes P3 et P4 de la refonte, [docs/refonte/interface.md](../../docs/refonte/interface.md)) :

| Greffon | Rôle | Bundle committé |
|---|---|---|
| `acp-interface` | Accueil à la place de la page « / », logotype « ACP », bannière d'alertes, verrou du français, contrôle de la version du SDK | `hermes/plugins/acp-interface/dashboard/dist/` |
| `acp-catalogue` | Onglet « Catalogue », en lecture seule | `hermes/plugins/acp-catalogue/dashboard/dist/` |
| `acp-projets` | Onglet « Projets » (P4) : lancer un projet, suivre son avancement, répondre aux questions, pauses ([docs/refonte/projets.md](../../docs/refonte/projets.md) § 4 bis) | `hermes/plugins/acp-projets/dashboard/dist/` |

Aucun n'a de code serveur : l'état et les gestes passent par le greffon `acp-poste` (`/v1/meta`,
`/v1/catalogue`, et depuis P4 `/v1/projets`, `/v1/questions`, `/v1/poste`, `/v1/pause`…) et par les
routes natives de Hermes (`/api/sessions`, `/api/skills`). React n'est
pas embarqué : il vient du SDK du tableau de bord (`window.__HERMES_PLUGIN_SDK__.React`).

Ce paquet est **hors des workspaces npm de la racine** : le verrou racine et le gel du moteur
Pixel Office n'en dépendent pas.

## Commandes

```sh
npm ci --ignore-scripts --prefix apps/interface   # dépendances de développement (verrou)
npm test --prefix apps/interface                  # TypeScript (tsc --noEmit) puis Vitest
npm run build --prefix apps/interface             # écrit les bundles sous hermes/plugins/
npm run check --prefix apps/interface             # échoue si un bundle committé est périmé
```

Après toute modification de `src/`, reconstruire et committer les bundles : la CI
(`ci.yml`, travail « Interface ACP ») reconstruit et refuse toute différence.

## Règles

- **Tout en français, d'un seul catalogue** : `src/chaines.ts`. Un texte écrit en dur dans un
  composant, une chaîne en enfant JSX ou un attribut lisible (`title`, `aria-label`…) écrit en
  dur fait échouer `tests/chaines.test.ts` (arbre syntaxique TypeScript). Typographie française :
  espace insécable avant « : ; ! ? » et dans les guillemets.
- **Aucune donnée inventée** : une valeur venue de l'API est rendue par `<Donnee>` (attribut
  `data-acp-donnee`) ; absente, elle s'affiche « Inconnu ». Le poste s'affiche « Non configuré »
  tant qu'il n'est pas branché (P5).
- **Aucun bouton sans route réelle et testée** : le Catalogue est en lecture seule ; chaque bouton de
  la page Projets appelle une route d'`acp-poste` couverte par les tests (Vitest, image, navigateur) ;
  un geste non encore livré n'a pas de bouton (relancer une carte bloquée : P7), et un bouton
  inutilisable est désactivé avec sa raison (notification de test sans canal configuré).
- **Rendu par React uniquement** : ni `dangerouslySetInnerHTML`, ni `innerHTML`, ni `eval`, ni
  `new Function`, ni `fetch` direct, ni stockage local, ni URL externe (`tests/statique.test.ts`,
  sur les sources ET les bundles). Les écritures passent par le `fetchJSON` du SDK, en JSON.
- **SDK contrôlé** : majeure 1 exigée (`sdkVersion` « 1.1.0 » en Hermes 0.21.5) ; sinon les
  greffons s'enregistrent comme un refus explicite.

## Outils

- `outils/exporter-chaines.mjs` : exporte le catalogue en JSON pour le test navigateur
  (`hermes/tests/e2e/test_interface_fr.py`).
- `outils/decompte-traductions.mjs` : décompte des chaînes de Hermes restées en anglais, mesuré
  sur les fichiers extraits de l'image épinglée (voir `docs/refonte/interface.md`).
