# Skills locales du dépôt

Trois skills de travail pour les agents de développement qui modifient ACP. Ce dossier en est la **seule source**.

| Skill | Pour quoi |
|---|---|
| [acp-changement-sur](acp-changement-sur/SKILL.md) | Règles de tout changement : lecture de l'état, commits, fins de ligne, moteur gelé, suites à lancer selon les chemins, Docker |
| [acp-themes-pixel](acp-themes-pixel/SKILL.md) | Thèmes, jetons, profils de mouvement et assets pixel : sources, générateurs, contrastes, contrôles, captures |
| [acp-espace-travail-qml](acp-espace-travail-qml/SKILL.md) | Conventions du shell QML de la station : modules, déclarations, singletons, `objectName`, textes, animations, layouts |

Chaque skill dit son déclencheur, ses entrées, ses étapes, ses sorties, ses limites et sa vérification. Les longues
listes vivent dans son dossier `references/`. Les numéros de ligne cités ont été relus le 11 octobre 2026.

## Pourquoi ici et pas sous `.claude`

- `CLAUDE.md:20` interdit de committer `.claude/`, et `.gitignore:50` l'ignore. Une skill de projet sous
  `.claude/skills/` ne serait donc jamais partagée.
- Un dossier neutre se lit par tout client : Claude Code, Codex, ou une personne qui relit.
- Ce sont des outils de l'agent de développement, l'« outillage A » de
  [docs/refonte/atelier-outillage.md](../../docs/refonte/atelier-outillage.md) § 1. Rien ici n'entre dans un produit
  livré. Aucune de ces skills n'est inscrite au catalogue de Hermes (`hermes/catalogue/catalogue.lock.json`), qui
  garde `skill-creator` exclue (D12) ; `scripts/verifier_catalogue.py` ne lit que `hermes/skills` (ligne 104).
  Aucun workflow n'exécute ces skills : seuls les contrôles d'hygiène de l'arbre suivi les liront une fois
  committées (`scripts/tests/test_fins_de_fichier.py`, balayage des secrets).

## Format

Structure de la skill `skill-creator` d'`anthropics/skills` (licence Apache 2.0) : en-tête YAML `name` et
`description`, corps court, références à part. Fichier lu le 11 octobre 2026 par raw.githubusercontent.com ; son
condensat SHA-256 (`dcd4803e…2bcf`) est celui que relève [atelier-outillage.md](../../docs/refonte/atelier-outillage.md)
§ 6.2. Aucun fichier de `skill-creator` n'est copié ici.

Contrôle fait le 11 octobre 2026 : le script `quick_validate.py` de `skill-creator`, lancé hors dépôt, rend « Skill
is valid! » pour les trois skills. La `description` de chacune compte moins de 1 024 caractères et ne contient aucun
chevron.

## Activer localement

La découverte des skills dépend du client et de sa version. Dans tous les cas : un **lien symbolique** vers ce
dossier, jamais une copie.

### Claude Code

Emplacement personnel : `~/.claude/skills/<nom>/SKILL.md`. Un lien symbolique y est admis : Claude Code lit le
`SKILL.md` de la cible (documentation « Extend Claude with skills », https://code.claude.com/docs/en/skills, lue
le 11 octobre 2026).

```sh
mkdir -p ~/.claude/skills
for nom in acp-changement-sur acp-themes-pixel acp-espace-travail-qml; do
  ln -s "$(pwd)/outils/skills/$nom" ~/.claude/skills/$nom
done
```

À lancer depuis la racine du dépôt. Selon la même documentation :

- une skill ajoutée sous `~/.claude/skills/` est vue pendant la session, sans redémarrage ; l'effet d'une
  modification faite à travers le lien n'a pas été vérifié ;
- une skill personnelle de même nom l'emporte sur une skill de projet ;
- les sessions cloud et Cowork ne lisent pas le `~/.claude/skills/` du poste. Dans une session cloud, créer le lien
  dans le conteneur de la session (non vérifié dans cette session), ou demander à l'agent de lire le `SKILL.md`
  voulu.

### Codex

Emplacements possibles : `~/.codex/skills/<nom>`, ou `.agents/skills/<nom>` à la racine du dépôt. **Non vérifié dans
cette session** : Codex n'y est pas installé, et sa documentation (developers.openai.com) y est bloquée par le réseau
([atelier-outillage.md](../../docs/refonte/atelier-outillage.md) § 2.1 et § 5). Consulter la documentation de la
version installée avant de créer le lien.

```sh
mkdir -p ~/.codex/skills
for nom in acp-changement-sur acp-themes-pixel acp-espace-travail-qml; do
  ln -s "$(pwd)/outils/skills/$nom" ~/.codex/skills/$nom
done
```

`.gitignore` n'ignore pas `.agents/` : un lien créé là apparaît comme non suivi. Ne jamais le committer.

## Une seule source

- Ne jamais copier une skill ailleurs dans le dépôt ; un lien symbolique local, hors suivi Git, suffit.
- Ne pas confondre avec `hermes/skills/` : ce sont les skills **du produit**, livrées dans l'image de Hermes et
  tenues par son catalogue ([docs/refonte/catalogue.md](../../docs/refonte/catalogue.md), lignes 18-19). Une skill
  de ce dossier n'y va jamais.
- Vérifier : `git ls-files '*SKILL.md' | grep -v '^hermes/skills/'` ne doit lister que des fichiers sous
  `outils/skills/`.
- Modifier une skill ici, dans une PR relue, comme tout document : français, LF, `git diff --check` propre.
- Une skill cite le code par `chemin:ligne`. Après un changement du code cité, relire ces lignes et les corriger.
