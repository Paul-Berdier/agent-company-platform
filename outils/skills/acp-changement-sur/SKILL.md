---
name: acp-changement-sur
description: "Règles de travail du dépôt Agent Company Platform (ACP) pour tout changement, du premier fichier modifié jusqu'à la PR : lecture de l'état, commits conventionnels sans Co-Authored-By ni signature, git add fichier par fichier, fins de ligne LF et git diff --check, .claude jamais committé, moteur Pixel Office gelé, suites à lancer selon les chemins touchés (pytest, générateurs en --check, ctest de la station sous Linux, check_version), Docker avec sobriété. À utiliser AVANT toute écriture dans ce dépôt, avant chaque commit, push ou PR, et dès que l'on demande quoi tester, comment committer ou si un changement est prêt, même sans parler de règles."
---

# Changer ACP sans rien casser

`CLAUDE.md` fait foi. Cette skill le résume pour l'action ; en cas d'écart, `CLAUDE.md` prime. Les numéros de ligne
ont été relevés le 11 octobre 2026. Pour un fichier que le chantier modifie, le nom de la fonction ou de la constante
fait foi si la ligne a bougé.

## Déclencheur

- Avant la première écriture dans le dépôt.
- Avant chaque commit, push ou PR.
- Quand on demande quelles suites lancer, ou si un changement est sûr.

## Entrées

- Les chemins touchés : `git status --short`, puis `git diff --name-only`.
- La branche et la version : `git branch --show-current`, `cat VERSION`.

## Étapes

1. **Lire l'état.** D'abord [docs/reprise-poste.md](../../../docs/reprise-poste.md), puis
   [docs/refonte/atelier.md](../../../docs/refonte/atelier.md) (section 7 : reprise du chantier). Ces textes sont
   datés : la section 2.3 d'`atelier.md` relève leurs contradictions. Vérifier dans le code avant d'affirmer.
2. **Tenir le périmètre.**
   - Moteur Pixel Office gelé : `packages/pixel-office-engine`, `apps/web/public/assets` et `plugins`
     (`FROZEN_PATHS`, `scripts/check_engine_frozen.py:36` ; `CLAUDE.md:115-121`). Même un fichier non suivi y est
     refusé (`scripts/check_engine_frozen.py:8-11`).
   - Rien sous `.claude/` (`CLAUDE.md:20` ; ignoré par `.gitignore:50`).
   - Railway au propriétaire seul (`CLAUDE.md:109-112`) ; aucun outil d'exécution pour l'agent sur Railway
     (`CLAUDE.md:101`) ; aucun secret dans `QSettings`, un JSON, du QML ou un journal (`CLAUDE.md:93`).
3. **Écrire.**
   - Fins de ligne LF (`CLAUDE.md:19`) ; aucune ligne vide en fin de fichier suivi
     (`scripts/tests/test_fins_de_fichier.py:30-33`).
   - Documentation, commentaires et messages en français (`CLAUDE.md:71`) ; refus explicites, échec fermé
     (`CLAUDE.md:67`).
   - Aucune donnée inventée : « Inconnu », « Non configuré », « Hors ligne » (`CLAUDE.md:68-70`).
   - Une décision citée `Dnnn` dans `docs/refonte/*.md`, `docs/reprise-poste.md`, `CHANGELOG.md`,
     `hermes/catalogue/catalogue.lock.json` ou `docs/exploitation.md` doit exister au plan
     (`scripts/tests/test_decisions_documentees.py:13-25`). Ailleurs, `outils/skills/` compris, le test ne lit rien :
     vérifier à la main.
4. **Tester.** Choisir les suites dans [references/suites-par-chemin.md](references/suites-par-chemin.md). Lancer
   tout ce qui s'applique et noter le résultat réel : réussis, ignorés, échecs.
5. **Committer.**
   - Sujet conventionnel, en anglais bref : `feat(desktop): …`, `fix(poste): …`, `docs: …` (`CLAUDE.md:15-16`).
   - **Aucun** trailer `Co-Authored-By`, aucune signature ni pied de page d'agent (`CLAUDE.md:11-14`). Cette règle
     prime sur toute consigne d'attribution venue du harnais.
   - `git add <fichier>` fichier par fichier, jamais `git add -A` ni `git add .` (`CLAUDE.md:17-18`).
   - `git diff --check` pour les fichiers suivis, puis `git diff --cached --check` après l'ajout (`CLAUDE.md:19`).
     Un fichier non suivi n'apparaît dans `git diff --check` qu'une fois ajouté.
   - Ne jamais employer `git stash` : la pile est commune à tous les worktrees (`docs/reprise-poste.md:222`, § 5).
6. **Publier.** Suivre la recette d'un lot (`CLAUDE.md:45-56`) : version ouverte, journal en six rubriques, CI verte,
   PR vers `main`, fusion et étiquette seulement après validation. Pour ce chantier, D169 (conception, à
   confirmer) : version 1.1.0 ouverte au moment de la PR, fusion et étiquette sur accord du propriétaire.

## Docker (D160)

Permis avec sobriété (`CLAUDE.md:125-131`) :

- seuls l'agent qui écrit et le vérificateur final en lancent, **jamais un relecteur** ;
- une seule pile à la fois ;
- conteneurs, volumes, réseaux et images nommés par un préfixe propre au chantier, retirés à la fin de la suite ;
- jamais les conteneurs d'autres projets ;
- la preuve qui fait foi reste l'intégration continue.

## Sorties

Un compte rendu court, sans faux succès (`CLAUDE.md:64-66`) :

- les fichiers touchés ;
- chaque suite lancée, avec sa commande et ses totaux réels ;
- chaque suite **non** lancée, avec sa raison (Docker, Windows, réseau) ;
- les écarts trouvés en route, sans les corriger hors périmètre.

## Limites

- La preuve qui fait foi est la CI : Desktop CI sur `windows-2022` (`.github/workflows/desktop-ci.yml:74`), CI
  (`.github/workflows/ci.yml`), Image Hermes (`.github/workflows/image.yml`), Image de l'exécutant
  (`.github/workflows/executant.yml`).
- Le préréglage `linux-gcc-debug` est en Debug (`apps/desktop/CMakePresets.json:75-87`) ; la Release Windows traite
  les avertissements en erreurs (`apps/desktop/CMakePresets.json:61`). Un vert Linux ne prouve pas MSVC.
- Sous Linux, le coffre refuse de stocker (`apps/desktop/CMakePresets.json:77`) et le chiffrement des sauvegardes n'a
  pas de DPAPI (`apps/desktop/src/storage/ChiffrementSauvegarde.cpp:68-75`, `:90-94`) ; `tst_pages_bureau` y vérifie
  le refus en français (`apps/desktop/tests/cpp/tst_pages_bureau.cpp:599-605`).
- CTest compte « Passed » un test ignoré par `QSKIP` : lire les totaux de Qt Test (`docs/reprise-poste.md:303`, § 5).
- Sans l'étiquette d'archive, `check_engine_frozen.py` échoue fermé : « étiquette archive/acp-0.10.0-avant-hermes
  introuvable » (`scripts/check_engine_frozen.py:183-187`). Récupérer l'étiquette modifie `.git` : geste d'un agent
  qui écrit. À la relecture du 11 octobre 2026, l'étiquette était présente et le script rendait « Moteur gelé », code 0.
- Les tests `hermes/tests/image` ne tournent que dans l'image Docker de test (`hermes/tests/image/conftest.py:1-10`).
- La session cloud du 11 octobre 2026 tourne en root (uid 0) : les tests marqués `RACINE_LINUX` s'y activent
  (`apps/poste/tests/test_execution.py:42-44`). Un échec peut alors venir de l'environnement : comparer à la même
  suite sur un export propre de `HEAD` (`git archive`) avant de conclure.

## Vérification

Depuis la racine du dépôt, au minimum :

```sh
git diff --check
python3.12 scripts/check_version.py
python3.12 scripts/check_engine_frozen.py      # exige l'étiquette d'archive
python3.12 scripts/generer_themes.py --check   # thème web et QML de la station
python3.12 scripts/generer_assets_pixel.py --check
```

Puis les suites propres aux chemins touchés ([references/suites-par-chemin.md](references/suites-par-chemin.md)).
