// Vérification de .railway/railway.ts SANS compte ni réseau : le fichier est évalué comme le fait
// la CLI Railway (Node, suppression des types TypeScript, SDK railway/iac de .railway/node_modules),
// puis le graphe obtenu est comparé à ce que le dépôt attend. Rien n'est planifié ni appliqué.
//
//   npm ci --ignore-scripts --prefix .railway
//   npm run --prefix .railway verifier           (tsc, puis ce script)
//   node --experimental-strip-types .railway/verifier.mjs [--graphe <fichier.json>]
//
// Ce qui est prouvé :
// 1. ÉCHEC FERMÉ : tant que les libellés valent leur gabarit, l'évaluation du fichier tel qu'il est
//    committé refuse, en français ; des libellés invalides, identiques, un autre environnement
//    que « production », un autre projet lié que « acp » (ou aucun) sont refusés de même ;
// 2. avec des libellés d'ESSAI (copie temporaire du fichier, supprimée ensuite), le graphe compte
//    exactement deux services et deux volumes, avec les réglages attendus (source, Wait for CI,
//    constructeur, santé, région, limites, politique de redémarrage, variables déclarées ou
//    preserve()), et AUCUNE Start Command, commande de pré-déploiement, domaine ni secret.
// --graphe écrit le graphe d'essai en JSON : hermes/tests/contrat/test_railway_iac_contrat.py
// démarre les deux images avec ses variables.
//
// Ce qui ne l'est PAS : ce que le moteur de la CLI (≥ 5.42.1) et Railway feront de ce graphe
// (clés non documentées, preserve() sur une variable neuve, région) : docs/refonte/railway.md § 3.

import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRailwayContext, project } from "railway/iac";

const ICI = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(ICI, "railway.ts");
const PREFIXE_REFUS = "[acp] REFUS (.railway/railway.ts) : ";

// Valeurs ATTENDUES, écrites ici indépendamment de railway.ts : toute modification de l'un exige
// la modification consciente de l'autre, dans la même PR.
const DEPOT = "Paul-Berdier/agent-company-platform";
const BRANCHE = "refonte/hermes";
const REGION = "europe-west4-drams3a";
const GABARITS = { LIBELLE_HERMES: "<libellé-hermes>", LIBELLE_IDENTITE: "<libellé-identite>" };
const ESSAI = { LIBELLE_HERMES: "essai-hermes-acp", LIBELLE_IDENTITE: "essai-identite-acp" };
const GIO = 1024 * 1024 * 1024;

const ATTENDU = {
  hermes: {
    racine: "/hermes",
    surveillance: ["/hermes/**", "!/hermes/tests/**"],
    relances: 10,
    cpu: 1,
    memoire: 2 * GIO,
    delaiSante: 300,
    volume: "hermes-donnees",
    montage: "/opt/data",
    litterales: (h, i) => ({
      PORT: "9119",
      RAILWAY_DOCKERFILE_PATH: "image/Dockerfile",
      RAILWAY_DEPLOYMENT_DRAINING_SECONDS: "20",
      HERMES_DASHBOARD_PUBLIC_URL: `https://${h}.up.railway.app`,
      HERMES_DASHBOARD_OIDC_ISSUER: `https://${i}.up.railway.app`,
      HERMES_DASHBOARD_OIDC_CLIENT_ID: "hermes-acp",
      HERMES_DASHBOARD_OIDC_SCOPES: "openid profile email offline_access",
    }),
    preservees: [],
  },
  identite: {
    racine: "/identite",
    surveillance: ["/identite/**"],
    relances: 100,
    cpu: 0.5,
    memoire: 2684354560,
    delaiSante: 120,
    volume: "identite-donnees",
    montage: "/config",
    litterales: (h, i) => ({
      PORT: "9091",
      RAILWAY_DEPLOYMENT_DRAINING_SECONDS: "10",
      ACP_IDP_DOMAINE: `${i}.up.railway.app`,
      ACP_HERMES_URL: `https://${h}.up.railway.app`,
    }),
    preservees: ["ACP_IDP_UTILISATEUR", "ACP_IDP_NOM", "ACP_IDP_EMAIL", "ACP_IDP_MOT_DE_PASSE_ARGON2"],
  },
};

// Clés admises, et elles seules : toute autre (startCommand, preDeployCommand, cronSchedule,
// networking, configFile…) fait échouer la vérification.
const CLES_NOEUD = ["address", "build", "deploy", "kind", "name", "source", "type", "variables", "volumeAttachments"];
const CLES_SOURCE = ["branch", "checkSuites", "repo", "rootDirectory", "type"];
const CLES_BUILD = ["builder", "watchPatterns"];
const CLES_DEPLOY = [
  "healthcheckPath",
  "healthcheckTimeout",
  "limitOverride",
  "multiRegionConfig",
  "restartPolicyMaxRetries",
  "restartPolicyType",
  "sleepApplication",
];
const SECRETS = [
  /\$argon2/i,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /\bsk-[A-Za-z0-9_-]{8,}/,
  /\bgh[pousr]_[A-Za-z0-9]{16,}/,
  /\bgithub_pat_/,
  /\bAKIA[0-9A-Z]{12,}/,
  /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/,
];

const erreurs = [];
const constats = [];
let essais = 0;

function exiger(condition, message) {
  if (!condition) erreurs.push(message);
}

function memes(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function cles(objet) {
  return Object.keys(objet ?? {}).sort();
}

function remplacer(texte, constante, valeur) {
  const motif = new RegExp(`^const ${constante} = "[^"\\n]*";$`, "m");
  const trouves = texte.match(new RegExp(motif.source, "gm")) ?? [];
  if (trouves.length !== 1) {
    throw new Error(`railway.ts doit déclarer « const ${constante} = "…"; » exactement une fois (${trouves.length} trouvée(s)).`);
  }
  return texte.replace(motif, `const ${constante} = ${JSON.stringify(valeur)};`);
}

function lireConstante(texte, constante) {
  const trouve = texte.match(new RegExp(`^const ${constante} = "([^"\\n]*)";$`, "m"));
  return trouve ? trouve[1] : null;
}

async function evaluerFichier(chemin, environnement, projet = "acp") {
  const module = await import(pathToFileURL(chemin).href);
  if (typeof module.default !== "function") {
    throw new Error("railway.ts n'exporte pas par défaut le programme de defineRailway().");
  }
  // projet === null : la CLI ne fournirait aucun nom de projet lié (ctx.projectName absent).
  const entree = { command: "plan", environment: environnement };
  if (projet !== null) entree.projectName = projet;
  const ctx = createRailwayContext(entree);
  return await module.default(ctx, project);
}

// Évalue une COPIE de railway.ts, libellés remplacés, dans .railway/ (pour que Node y résolve
// railway/iac) sous un nom ignoré par Git ; la copie est toujours supprimée.
async function evaluerCopie(libelles, environnement = "production", projet = "acp") {
  let texte = readFileSync(SOURCE, "utf8");
  for (const [constante, valeur] of Object.entries(libelles)) texte = remplacer(texte, constante, valeur);
  essais += 1;
  const copie = join(ICI, `.essai-${process.pid}-${essais}.ts`);
  writeFileSync(copie, texte, "utf8");
  try {
    return await evaluerFichier(copie, environnement, projet);
  } finally {
    rmSync(copie, { force: true });
  }
}

async function attendreRefus(titre, evaluation, fragment) {
  try {
    await evaluation();
  } catch (erreur) {
    const message = erreur instanceof Error ? erreur.message : String(erreur);
    exiger(message.startsWith(PREFIXE_REFUS), `${titre} : refus inattendu (« ${message} »).`);
    exiger(message.includes(fragment), `${titre} : le refus ne mentionne pas « ${fragment} » (« ${message} »).`);
    constats.push(`refus attendu — ${titre} : ${message}`);
    return;
  }
  erreurs.push(`${titre} : l'évaluation a RÉUSSI au lieu de refuser (échec fermé rompu).`);
}

function verifierService(noeud, nom, h, i) {
  const a = ATTENDU[nom];
  const ici = `service ${nom}`;
  // Le SDK laisse une table volumeMounts VIDE à côté des volumeAttachments : admise vide seulement
  // (un montage brut, sans volume déclaré, n'a rien à faire ici).
  const { volumeMounts, ...reste } = noeud;
  exiger(volumeMounts === undefined || memes(volumeMounts, {}), `${ici} : montage brut inattendu ${JSON.stringify(volumeMounts)}.`);
  exiger(memes(cles(reste), [...CLES_NOEUD].sort()), `${ici} : clés ${JSON.stringify(cles(reste))}, attendu ${JSON.stringify(CLES_NOEUD)} (aucun domaine, aucune configuration de fichier).`);
  exiger(noeud.kind === "github", `${ici} : source de type « ${noeud.kind} », attendu « github ».`);

  const s = noeud.source ?? {};
  exiger(memes(cles(s), [...CLES_SOURCE].sort()), `${ici} : clés de source ${JSON.stringify(cles(s))}.`);
  exiger(s.type === "github" && s.repo === DEPOT, `${ici} : dépôt « ${s.repo} », attendu « ${DEPOT} ».`);
  exiger(s.branch === BRANCHE, `${ici} : branche « ${s.branch} », attendu « ${BRANCHE} ».`);
  exiger(s.rootDirectory === a.racine, `${ici} : répertoire racine « ${s.rootDirectory} », attendu « ${a.racine} ».`);
  exiger(s.checkSuites === true, `${ici} : checkSuites (Wait for CI) doit valoir true.`);

  const b = noeud.build ?? {};
  exiger(memes(cles(b), [...CLES_BUILD].sort()), `${ici} : clés de construction ${JSON.stringify(cles(b))}.`);
  exiger(b.builder === "DOCKERFILE", `${ici} : constructeur « ${b.builder} », attendu « DOCKERFILE ».`);
  exiger(memes(b.watchPatterns, a.surveillance), `${ici} : motifs surveillés ${JSON.stringify(b.watchPatterns)}.`);

  const d = noeud.deploy ?? {};
  exiger(memes(cles(d), [...CLES_DEPLOY].sort()), `${ici} : clés de déploiement ${JSON.stringify(cles(d))}, attendu ${JSON.stringify(CLES_DEPLOY)} (aucune Start Command ni pré-déploiement).`);
  exiger(d.healthcheckPath === "/api/health", `${ici} : chemin de santé « ${d.healthcheckPath} ».`);
  exiger(d.healthcheckTimeout === a.delaiSante, `${ici} : délai de santé ${d.healthcheckTimeout}, attendu ${a.delaiSante}.`);
  exiger(d.sleepApplication === false, `${ici} : sleepApplication (Serverless) doit valoir false.`);
  exiger(d.restartPolicyType === "ON_FAILURE", `${ici} : politique de redémarrage « ${d.restartPolicyType} ».`);
  exiger(d.restartPolicyMaxRetries === a.relances, `${ici} : ${d.restartPolicyMaxRetries} relances, attendu ${a.relances}.`);
  exiger(memes(d.limitOverride, { containers: { cpu: a.cpu, memoryBytes: a.memoire } }), `${ici} : limites ${JSON.stringify(d.limitOverride)}.`);
  exiger(memes(d.multiRegionConfig, { [REGION]: { numReplicas: 1 } }), `${ici} : répliques ${JSON.stringify(d.multiRegionConfig)}, attendu une seule en ${REGION}.`);

  const attaches = noeud.volumeAttachments ?? {};
  exiger(
    memes(attaches, { [a.volume]: { volume: `volume.${a.volume}`, mountPath: a.montage, volumeConfig: { region: REGION } } }),
    `${ici} : montage ${JSON.stringify(attaches)}, attendu ${a.volume} sur ${a.montage}.`,
  );

  const variables = noeud.variables ?? {};
  const litterales = a.litterales(h, i);
  const attendues = [...Object.keys(litterales), ...a.preservees].sort();
  exiger(memes(cles(variables), attendues), `${ici} : variables ${JSON.stringify(cles(variables))}, attendu ${JSON.stringify(attendues)}.`);
  for (const [cle, valeur] of Object.entries(litterales)) {
    exiger(memes(variables[cle], { type: "literal", value: valeur }), `${ici} : ${cle} = ${JSON.stringify(variables[cle])}, attendu la valeur littérale « ${valeur} ».`);
  }
  for (const cle of a.preservees) {
    exiger(memes(variables[cle], { type: "preserve" }), `${ici} : ${cle} doit être preserve() (valeur posée dans Railway, jamais dans Git).`);
  }
  for (const [cle, valeur] of Object.entries(variables)) {
    const texte = JSON.stringify(valeur);
    for (const motif of SECRETS) exiger(!motif.test(texte), `${ici} : ${cle} ressemble à un secret (${motif}).`);
  }
}

function verifierGraphe(definition, h, i) {
  const avant = erreurs.length;
  exiger(definition?.name === "acp", `projet « ${definition?.name} », attendu « acp ».`);
  const ressources = definition?.resources ?? [];
  const adresses = ressources.map((r) => r.address).sort();
  exiger(
    memes(adresses, ["service.hermes", "service.identite", "volume.hermes-donnees", "volume.identite-donnees"]),
    `ressources ${JSON.stringify(adresses)} : exactement deux services et deux volumes attendus (toute ressource omise serait SUPPRIMÉE à l'apply).`,
  );
  for (const r of ressources) {
    if (r.type === "volume") {
      exiger(memes(r.config, { region: REGION }), `volume ${r.name} : configuration ${JSON.stringify(r.config)}, attendu la région ${REGION}.`);
    }
    if (r.type === "service" && (r.name === "hermes" || r.name === "identite")) verifierService(r, r.name, h, i);
  }
  return erreurs.length === avant;
}

async function principal() {
  const arguments_ = process.argv.slice(2);
  let fichierGraphe = null;
  for (let n = 0; n < arguments_.length; n += 1) {
    if (arguments_[n] === "--graphe" && n + 1 < arguments_.length) {
      fichierGraphe = arguments_[n + 1];
      n += 1;
    } else {
      throw new Error(`argument inconnu : « ${arguments_[n]} » (seul --graphe <fichier.json> est admis).`);
    }
  }

  // 1. Le fichier tel qu'il est committé.
  const texte = readFileSync(SOURCE, "utf8");
  const h = lireConstante(texte, "LIBELLE_HERMES");
  const i = lireConstante(texte, "LIBELLE_IDENTITE");
  exiger(h !== null && i !== null, "railway.ts doit déclarer LIBELLE_HERMES et LIBELLE_IDENTITE en chaînes littérales.");
  if (h === GABARITS.LIBELLE_HERMES || i === GABARITS.LIBELLE_IDENTITE) {
    constats.push("railway.ts porte encore au moins un libellé de gabarit : son évaluation DOIT refuser.");
    await attendreRefus("fichier committé (gabarits)", () => evaluerFichier(SOURCE, "production"), "vaut encore le gabarit");
  } else {
    constats.push(`railway.ts porte les libellés du propriétaire : ${h} et ${i}.`);
    if (verifierGraphe(await evaluerFichier(SOURCE, "production"), h, i)) {
      constats.push("graphe du fichier committé conforme.");
    }
  }

  // 2. Refus : chaque libellé, séparément, et l'environnement.
  await attendreRefus("libellé Hermes de gabarit", () => evaluerCopie({ ...ESSAI, LIBELLE_HERMES: GABARITS.LIBELLE_HERMES }), "LIBELLE_HERMES vaut encore le gabarit");
  await attendreRefus("libellé identité de gabarit", () => evaluerCopie({ ...ESSAI, LIBELLE_IDENTITE: GABARITS.LIBELLE_IDENTITE }), "LIBELLE_IDENTITE vaut encore le gabarit");
  await attendreRefus("majuscules", () => evaluerCopie({ ...ESSAI, LIBELLE_HERMES: "Essai-Hermes" }), "libellé DNS");
  await attendreRefus("point (hôte complet)", () => evaluerCopie({ ...ESSAI, LIBELLE_IDENTITE: "essai.up.railway.app" }), "libellé DNS");
  await attendreRefus("tiret initial", () => evaluerCopie({ ...ESSAI, LIBELLE_HERMES: "-essai" }), "libellé DNS");
  await attendreRefus("libellé vide", () => evaluerCopie({ ...ESSAI, LIBELLE_IDENTITE: "" }), "libellé DNS");
  await attendreRefus("64 caractères", () => evaluerCopie({ ...ESSAI, LIBELLE_HERMES: "a".repeat(64) }), "libellé DNS");
  await attendreRefus("libellés identiques", () => evaluerCopie({ LIBELLE_HERMES: "essai-acp", LIBELLE_IDENTITE: "essai-acp" }), "même sous-domaine");
  await attendreRefus("environnement staging", () => evaluerCopie(ESSAI, "staging"), "seul « production »");
  await attendreRefus("autre projet lié", () => evaluerCopie(ESSAI, "production", "autre-projet"), "le projet lié est « autre-projet »");
  await attendreRefus("projet lié inconnu", () => evaluerCopie(ESSAI, "production", null), "le projet lié est « undefined »");

  // 3. Graphe avec des libellés d'essai valides.
  const graphe = await evaluerCopie(ESSAI);
  if (verifierGraphe(graphe, ESSAI.LIBELLE_HERMES, ESSAI.LIBELLE_IDENTITE)) {
    constats.push(
      `graphe d'essai conforme (${ESSAI.LIBELLE_HERMES}, ${ESSAI.LIBELLE_IDENTITE}) : 2 services, 2 volumes, ` +
        `région ${REGION}, branche ${BRANCHE}, Wait for CI, DOCKERFILE, aucune Start Command.`,
    );
  }
  if (fichierGraphe) {
    writeFileSync(fichierGraphe, `${JSON.stringify({ libelles: ESSAI, projet: graphe }, null, 2)}\n`, "utf8");
    constats.push(`graphe d'essai écrit dans ${fichierGraphe}.`);
  }

  for (const ligne of constats) console.log(`[verifier] ${ligne}`);
  if (erreurs.length > 0) {
    for (const ligne of erreurs) console.error(`[verifier] ÉCHEC : ${ligne}`);
    console.error(`[verifier] ${erreurs.length} écart(s) : .railway/railway.ts n'est PAS conforme.`);
    process.exitCode = 1;
    return;
  }
  console.log("[verifier] .railway/railway.ts conforme : échec fermé tant que les gabarits restent, graphe attendu sinon.");
}

principal().catch((erreur) => {
  console.error(`[verifier] ÉCHEC : ${erreur instanceof Error ? erreur.stack ?? erreur.message : String(erreur)}`);
  process.exitCode = 1;
});
