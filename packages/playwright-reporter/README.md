# `@acp/playwright-reporter`

Reporter Playwright de la plateforme. Il écrit un **NDJSON local** que le worker
authentifié ingère ; il ne parle jamais au réseau et ne porte **aucun credential**.

## Prérequis

Playwright (≥ 1.44) est installé **sur le runner**, par l'équipe qui possède la suite de
tests — jamais par la plateforme. Ce paquet n'a **aucune dépendance** : il implémente
l'interface `Reporter` par sa forme et n'importe pas `@playwright/test`, qui n'est donc
pas ajouté au dépôt.

## Configuration

Dans `playwright.config.ts` du dépôt testé :

```ts
export default defineConfig({
  reporter: [["@acp/playwright-reporter"]],
});
```

Le reporter peut être combiné à d'autres (`[["list"], ["@acp/playwright-reporter"]]`) :
il n'écrit rien sur la sortie standard (`printsToStdio()` renvoie `false`).

Le fichier de sortie est désigné par la variable d'environnement **`ACP_REPORT_FILE`**,
positionnée par le worker :

```text
ACP_REPORT_FILE=<répertoire de sortie de la tentative>/report.ndjson
```

Si la variable est absente ou vide, le reporter écrit **une** ligne d'avertissement sur
`stderr` et se désactive : l'exécution des tests n'est jamais mise en échec par le
reporter. Il en va de même si le fichier devient inaccessible en cours d'exécution.

### Chemin des pièces jointes

Une pièce jointe portant un fichier n'est retenue que si ce fichier se trouve **sous le
répertoire du rapport** (`dirname(ACP_REPORT_FILE)`) ; son chemin est alors publié
relatif et en séparateurs POSIX. Une pièce jointe hors de ce répertoire est **signalée
par une ligne `error` et ignorée** : son chemin absolu n'est jamais recopié, il
décrirait l'arborescence du runner.

Configurez donc la sortie de Playwright sous le même répertoire, par exemple :

```ts
import { dirname, join } from "node:path";

const reportFile = process.env.ACP_REPORT_FILE;

export default defineConfig({
  outputDir: reportFile ? join(dirname(reportFile), "test-results") : "test-results",
  reporter: [["@acp/playwright-reporter"]],
});
```

ou, plus simplement, en lançant `playwright test --output=<répertoire>/test-results`.

Une pièce jointe **sans fichier** (corps en mémoire, `testInfo.attach(nom, { body })`)
est elle aussi signalée par une ligne `error` et ignorée : le contrat d'ingestion
(`acp_contracts.testing.ReporterAttachment`, `extra="forbid"`) exige un `path` et ne
connaît aucun champ de corps encodé. Embarquer le corps ferait refuser la ligne
`test_end` **entière** — donc le statut, l'issue et l'erreur du test avec elle. Pour
qu'une pièce jointe soit publiée, écrivez-la sur disque sous le répertoire de rapport :

```ts
await testInfo.attach("diagnostic", { path: join(testInfo.outputDir, "diagnostic.json") });
```

## Format de sortie

Une ligne JSON par événement, ajoutée en synchrone (`appendFileSync`) pour qu'un
processus interrompu laisse un rapport exploitable. L'ajout n'étant atomique que pour de
petites écritures, une exécution répartie en shards doit donner à **chaque shard son
propre `ACP_REPORT_FILE`** ; le worker concatène les rapports. Quatre variantes de
`kind` :

| `kind` | Émis par | Contenu |
|---|---|---|
| `run_begin` | `onBegin` | `started_at`, `runner_version`, `config` (version, `workers`, `shard`, projets et base URL sans identifiants) |
| `test_end` | `onTestEnd` | identité stable, statut brut **et** issue calculée, durée, erreur, étapes, annotations, pièces jointes |
| `error` | `onError` et les pièces jointes refusées | `message` borné à 2000 caractères |
| `run_end` | `onEnd` | `finished_at`, `run_status`, `totals` |

Exemple :

```json
{"kind":"run_begin","started_at":"2026-09-12T17:59:47.601Z","runner_version":"1.55.0","config":{"version":"1.55.0","workers":4,"shard":{"current":1,"total":2},"projects":[{"name":"chromium","base_url":"https://app.example.test/"}]}}
{"kind":"test_end","test_id":"dashboard-affiche-1","title":"affiche les indicateurs","suite_path":["chromium","tests/dashboard.spec.ts","tableau de bord"],"location":{"file":"tests/dashboard.spec.ts","line":12,"column":3},"project_name":"chromium","attempt":2,"expected_status":"passed","status":"passed","outcome":"flaky","duration_ms":2870,"error_message":"","error_snippet":"","steps":[{"title":"ouvre /dashboard","category":"test.step","duration_ms":880,"error":false}],"annotations":[],"attachments":[]}
{"kind":"error","message":"Error: worker process exited unexpectedly"}
{"kind":"run_end","finished_at":"2026-09-12T17:59:47.626Z","run_status":"failed","totals":{"expected":0,"unexpected":0,"flaky":1,"skipped":1,"interrupted":0,"timedOut":0}}
```

### Statuts et issues

Le statut brut de la tentative (`passed`, `failed`, `timedOut`, `skipped`,
`interrupted`) est conservé tel quel à côté de l'issue calculée (`expected`,
`unexpected`, `flaky`, `skipped`) : rien n'est réduit à « vert / rouge ». L'issue suit
l'algorithme de Playwright — les tentatives ignorées et interrompues ne comptent pas ;
un test dont toutes les tentatives retenues valent le statut attendu est `expected`, un
test dont une seule y parvient est `flaky`. Une ligne est écrite **par tentative**
(`attempt = result.retry + 1`), donc la première tentative d'un test instable porte
`outcome: "unexpected"` et la reprise réussie porte `outcome: "flaky"`.

`totals` se lit sur la **dernière** tentative de chaque test : `expected`, `unexpected`,
`flaky` et `skipped` comptent les issues, tandis que `interrupted` et `timedOut`
comptent les statuts bruts — un test interrompu compte donc dans `skipped` (issue) et
dans `interrupted` (statut), exactement comme Playwright le rapporte.

`exit_code` et `report_path` ne sont **pas** émis : le code de sortie appartient au
processus, que seul le worker observe.

### Bornes

`error_message` et `error_snippet` sont débarrassés des séquences ANSI puis tronqués à
8000 caractères (marque `…[tronqué]` comprise). Aucune coupe ne casse une paire de
substitution UTF-16 : une demi-paire n'étant pas encodable en UTF-8, elle ferait rejeter
la ligne entière par le contrat (`string_unicode`). Un emoji en fin de coupe est donc
retiré, et la valeur peut mesurer un caractère de moins que la borne. Les étapes sont
bornées à 200, les annotations et les pièces jointes à 50, le chemin de suite à 20
niveaux. Les bornes correspondent à `acp_contracts.testing`.

## Ce que le reporter ne fait pas

- **Aucun appel réseau.** Le NDJSON est local ; c'est le worker authentifié qui publie.
- **Aucun credential.** Le reporter n'en reçoit pas et n'en transporte pas.
- **Aucune lecture de l'environnement** en dehors de `ACP_REPORT_FILE` : ni les variables
  d'environnement, ni les en-têtes de requête, ni `stdout`/`stderr` des tests
  (`onStdOut`/`onStdErr` ne sont volontairement pas implémentés) n'entrent dans le
  rapport.
- **Aucune autre écriture** que ses lignes NDJSON.
- **Aucun échec provoqué** : toute erreur interne dégrade le rapport et se résume à une
  ligne sur `stderr`.
- La base URL publiée dans `run_begin` est privée de ses identifiants, de sa requête et
  de son fragment ; `location.file` est relatif à `rootDir`, à défaut réduit au nom de
  fichier, et le chemin d'une pièce jointe hors du répertoire de rapport n'est jamais
  recopié.

### Ce que le nettoyage des chemins couvre — et ne couvre pas

`error_message` et `error_snippet` sont republiés **tels que le runner les a produits**,
à trois transformations près : séquences ANSI retirées, occurrences de `rootDir`
réécrites en chemin relatif (`C:\projets\app\tests\a.spec.ts` ⇒ `tests\a.spec.ts`), puis
troncature. Un chemin absolu **hors** de `rootDir` — internes de Playwright, `node_modules`
d'un autre volume, fichier ouvert par le test — reste tel quel : le reporter ne le devine
pas et préfère ne pas mutiler une assertion. Une suite de tests qui manipule des chemins
sensibles doit donc les expurger côté test ; la rédaction de la plateforme
(`acp_contracts.redaction`) s'applique ensuite côté worker et API.

## Tests

```text
npm test --workspace @acp/playwright-reporter
```

Aucun navigateur, aucun Playwright réel : les objets `TestCase`, `TestResult`,
`TestStep`, `FullConfig` et `FullResult` sont synthétiques.

Le paquet n'ayant aucune dépendance, `tools/run-vitest.mjs` démarre la Vitest déjà
installée dans le dépôt (elle n'est pas remontée à la racine) ; il n'installe rien et
ne sort pas du dépôt.
