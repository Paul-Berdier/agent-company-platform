// Infrastructure as Code (IaC) du déploiement Railway d'ACP — étape P2 de la refonte.
//
// Un projet « acp », un environnement « production », deux services construits depuis ce dépôt,
// chacun avec son volume :
//   - « hermes »   : hermes/image/Dockerfile (contexte hermes/), volume « hermes-donnees » sur /opt/data ;
//   - « identite » : identite/Dockerfile (contexte identite/), volume « identite-donnees » sur /config.
// Procédure complète, en français, pour le propriétaire : docs/refonte/railway.md.
//
// Appliqué UNIQUEMENT par le propriétaire, depuis son poste ; jamais par la CI ni par un agent :
//   gh run list --workflow image.yml --commit <sha de tête>   → « success » exigé
//   npm ci --ignore-scripts --prefix .railway
//   railway config plan --verbose                              → « 0 to destroy » exigé
//   railway config apply                                       → confirmation interactive, jamais --yes
// Railway ne lit JAMAIS ce fichier au déploiement : il ne sert qu'au plan et à l'apply.
// Fichier de projet ENTIER : une ressource omise ici serait SUPPRIMÉE au prochain apply
// (rw_full.txt:28156) ; détacher ou supprimer un volume est destructif (rw_full.txt:28708).
// AUCUN apply entre une restauration de sauvegarde et la PR qui réaligne ce fichier (railway.md § 10).
// Jamais `railway config pull` sans --json : il RÉÉCRIRAIT ce fichier (gardes et commentaires perdus).
//
// ÉCHEC FERMÉ. Tant que les libellés des deux sous-domaines *.up.railway.app valent leur gabarit,
// l'évaluation refuse, en français : plan et apply échouent sans rien changer. Les deux images
// refusent aussi de démarrer sur une valeur de gabarit ou sur un domaine privé.
//
// Aucun secret : l'identité du propriétaire est posée dans Railway (empreinte Argon2 SCELLÉE) et
// déclarée ici par preserve(), « garder la valeur déjà posée dans Railway ».
//
// Clés typées par le SDK railway@3.11.0 mais absentes de la documentation de l'IaC : checkSuites
// (Wait for CI), build.builder, build.watchPatterns, deploy.sleepApplication,
// deploy.restartPolicyType, deploy.restartPolicyMaxRetries, deploy.limitOverride. Leur prise en
// compte se prouve après l'apply par `railway config pull --json` ; sinon réglage à la main, puis
// `railway config plan --detailed-exit-code` doit rendre 0 (railway.md § 3).
//
// AUCUNE Start Command : ni start, ni startCommand, ni run.command, ni deploy.startCommand
// (scripts/tests/test_railway_iac.py). Une Start Command remplace l'ENTRYPOINT, donc les gardes ;
// la seule admise est celle de maintenance, posée à la main puis retirée (railway.md § 10).
//
// Vérifié en CI (image.yml) : `tsc` (typage contre le SDK) et .railway/verifier.mjs, qui évalue ce
// fichier comme le fait la CLI (Node, suppression des types) : refus des gabarits, puis graphe
// attendu avec des libellés d'essai.
import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

const DEPOT = "Paul-Berdier/agent-company-platform";

// Décision du propriétaire (25/09/2026) : la branche déployée est refonte/hermes, après la fusion
// de P2. Railway construit chaque commit poussé sur cette branche, après « Wait for CI ».
const BRANCHE = "refonte/hermes";

// Seul projet admis (relecture P2) : ce fichier décrit un projet ENTIER ; évalué pour un autre projet
// lié par erreur (lien interactif, homonyme d'un autre espace), le plan y supprimerait tout ce qui
// n'est pas décrit ici. La CLI fournit le nom du projet lié (ctx.projectName, rw_full.txt:28476) ;
// son absence refuse aussi. L'identifiant du projet n'est pas vérifié : il n'existe qu'après
// `railway init` (railway.md § 4.2) ; la lecture de « 0 to destroy » reste obligatoire.
const PROJET = "acp";

// Seul environnement admis : un plan lié à un autre environnement refuse.
const ENVIRONNEMENT = "production";

// EU West Metal, Amsterdam : identifiant de la page « Regions » (rw_full.txt:30283), présenté
// comme « the value that can be used in your Config as Code file ». La référence de l'IaC montre
// aussi "europe-west4" (rw_full.txt:28596) : ambiguïté documentée (railway.md § 3). Si le plan
// refuse cet identifiant, le repli "europe-west4" passe par une PR, jamais par un réglage manuel.
const REGION = "europe-west4-drams3a";

// Libellés des sous-domaines *.up.railway.app, choisis par le PROPRIÉTAIRE et figés AVANT tout
// enrôlement de passkey : une passkey est liée au sous-domaine exact de l'identité. À remplacer,
// par une PR, par deux libellés DNS distincts (a-z, 0-9, tirets ; 63 caractères au plus ; ni
// tiret initial ni final) : railway.md § 4. Tant qu'ils valent le gabarit, tout est refusé.
const LIBELLE_HERMES = "<libellé-hermes>";
const LIBELLE_IDENTITE = "<libellé-identite>";

const GIO = 1024 * 1024 * 1024;

// Limites des répliques (Hobby : 8 vCPU et 8 Go par réplique au plus, rw_full.txt:30848).
// Hermes : décision du propriétaire, 2 Go et 1 vCPU (415 à 440 Mio mesurés au repos).
// identite : 2,5 Gio MESURÉS (docs/refonte/identite.md § 8 ; test_memoire_premier_facteur_concurrent) :
// 20 premiers facteurs simultanés montent à ~1,35 Gio, sous les deux tiers de la limite ; 1 Go est
// tué (OOM) dans le témoin. 0,5 vCPU : décision du propriétaire.
const MEMOIRE_HERMES = 2 * GIO;
const MEMOIRE_IDENTITE = (5 * GIO) / 2;

const LIBELLE_DNS = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

function refuser(motif: string): never {
  throw new Error(`[acp] REFUS (.railway/railway.ts) : ${motif} Rien n'est planifié ni appliqué.`);
}

function libelle(nom: string, valeur: string): string {
  if (valeur.includes("<") || valeur.includes(">")) {
    refuser(
      `${nom} vaut encore le gabarit « ${valeur} ». Choisissez le libellé du sous-domaine ` +
        "*.up.railway.app et remplacez-le par une PR, CI verte (docs/refonte/railway.md § 4).",
    );
  }
  if (!LIBELLE_DNS.test(valeur)) {
    refuser(
      `${nom} vaut « ${valeur} » : un libellé DNS compte de 1 à 63 caractères parmi a-z, 0-9 et ` +
        "le tiret, sans tiret au début ni à la fin (ni point, ni majuscule, ni schéma).",
    );
  }
  return valeur;
}

export default defineRailway((ctx) => {
  if (ctx.projectName !== PROJET) {
    refuser(
      `le projet lié est « ${String(ctx.projectName)} » ; ce fichier décrit le projet ENTIER « ${PROJET} », et ` +
        "l'appliquer à un autre projet y supprimerait toutes les ressources qu'il ne décrit pas " +
        "(railway link --project acp --environment production).",
    );
  }
  if (ctx.environment !== ENVIRONNEMENT) {
    refuser(
      `l'environnement lié est « ${String(ctx.environment)} » ; seul « ${ENVIRONNEMENT} » est décrit ` +
        "par ce fichier (railway link --environment production).",
    );
  }

  const domaineHermes = `${libelle("LIBELLE_HERMES", LIBELLE_HERMES)}.up.railway.app`;
  const domaineIdentite = `${libelle("LIBELLE_IDENTITE", LIBELLE_IDENTITE)}.up.railway.app`;
  if (domaineHermes === domaineIdentite) {
    refuser(
      "LIBELLE_HERMES et LIBELLE_IDENTITE désignent le même sous-domaine : Hermes et le fournisseur " +
        "d'identité ont chacun le leur.",
    );
  }
  // URL publiques : toujours https, sans barre finale (validées aussi par les gardes des images).
  const urlHermes = `https://${domaineHermes}`;
  const urlIdentite = `https://${domaineIdentite}`;

  const donneesHermes = volume("hermes-donnees", { region: REGION });
  const donneesIdentite = volume("identite-donnees", { region: REGION });

  const hermes = service("hermes", {
    // checkSuites : « Wait for CI » (rw_full.txt:29670-29707) : un commit n'est déployé qu'après
    // la fin de TOUS les workflows GitHub Actions du commit ; un échec saute le déploiement.
    source: github(DEPOT, { branch: BRANCHE, rootDirectory: "/hermes", checkSuites: true }),
    build: {
      // DOCKERFILE : le build échoue plutôt que de laisser Railpack deviner (supposé ; le journal
      // de build doit le confirmer).
      builder: "DOCKERFILE",
      // Motifs partant de la racine du dépôt, même avec un répertoire racine (rw_full.txt:28930).
      // Les tests ne sont pas dans l'image (hermes/.dockerignore) : ils ne déclenchent rien.
      watchPatterns: ["/hermes/**", "!/hermes/tests/**"],
    },
    deploy: {
      sleepApplication: false,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 10,
      limitOverride: { containers: { cpu: 1, memoryBytes: MEMOIRE_HERMES } },
    },
    // Route publique de Hermes : 200 et {"ok": true, …}, y compris avec l'hôte
    // healthcheck.railway.app (hermes/tests/contrat/test_railway_iac_contrat.py).
    healthcheck: "/api/health",
    healthcheckTimeout: 300,
    replicas: { [REGION]: 1 },
    volumeMounts: { "/opt/data": donneesHermes },
    env: {
      // Port sondé par Railway (santé) et port cible du domaine : 9119, fixé par l'image.
      PORT: "9119",
      // Relatif au répertoire racine /hermes (à confirmer au premier build : railway.md § 4).
      RAILWAY_DOCKERFILE_PATH: "image/Dockerfile",
      RAILWAY_DEPLOYMENT_DRAINING_SECONDS: "20",
      HERMES_DASHBOARD_PUBLIC_URL: urlHermes,
      HERMES_DASHBOARD_OIDC_ISSUER: urlIdentite,
      HERMES_DASHBOARD_OIDC_CLIENT_ID: "hermes-acp",
      HERMES_DASHBOARD_OIDC_SCOPES: "openid profile email offline_access",
    },
  });

  const identite = service("identite", {
    source: github(DEPOT, { branch: BRANCHE, rootDirectory: "/identite", checkSuites: true }),
    build: { builder: "DOCKERFILE", watchPatterns: ["/identite/**"] },
    deploy: {
      // Un fournisseur d'identité endormi ferait répondre 503 à Hermes.
      sleepApplication: false,
      restartPolicyType: "ON_FAILURE",
      // Décision du propriétaire : 100 relances (toute valeur est admise sur une offre payante,
      // rw_full.txt:30006).
      restartPolicyMaxRetries: 100,
      limitOverride: { containers: { cpu: 0.5, memoryBytes: MEMOIRE_IDENTITE } },
    },
    healthcheck: "/api/health",
    healthcheckTimeout: 120,
    replicas: { [REGION]: 1 },
    volumeMounts: { "/config": donneesIdentite },
    env: {
      PORT: "9091",
      RAILWAY_DEPLOYMENT_DRAINING_SECONDS: "10",
      ACP_IDP_DOMAINE: domaineIdentite,
      ACP_HERMES_URL: urlHermes,
      // Posées par le propriétaire dans Railway (railway.md § 5), jamais écrites ici.
      ACP_IDP_UTILISATEUR: preserve(),
      ACP_IDP_NOM: preserve(),
      ACP_IDP_EMAIL: preserve(),
      ACP_IDP_MOT_DE_PASSE_ARGON2: preserve(), // variable SCELLÉE
    },
  });

  return project(PROJET, { resources: [hermes, identite, donneesHermes, donneesIdentite] });
});
