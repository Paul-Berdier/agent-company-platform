// File « Questions » (étape P7, cahier P7 § 3) : cinq sections sur une page, dans cet ordre.
// 1. Questions ouvertes ou escaladées (GET /v1/questions) : texte, contexte, projet, carte, QUI y répond (règle unique
//    du greffon, ``chez`` : « Hermes y répond » si sa carte « répondre » existe, « À vous » sinon ; jamais d'après le
//    réglage courant du projet), et la réponse du propriétaire (POST /v1/questions/{q}/reponse), toujours possible ;
// 2. Décisions (cartes en triage) : « Prolonger » ou « Relancer la planification » avec une consigne facultative,
//    « Conclure le projet » ; « Reprendre » pour une autre carte en triage ;
// 3. Revues des fichiers de pilotage (étape P6) : « Accepter », « Refuser » (motif exigé) ; le diff reste sur
//    l'exécutant, et la page le dit ;
// 4. Cartes arrêtées (bloquées ou abandonnées) : « Relancer » avec une consigne facultative
//    (POST /v1/cartes/{tableau}/{carte}/relancer), ou la raison pour laquelle la carte ne se relance pas ; une carte
//    bloquée pour un secret (partie E, K25) dit que son travail reste en quarantaine et que la relance repart d'une
//    branche neuve ;
// 5. Discussions en attente : sessions du tableau de bord dont une requête au client est ouverte, lues par le JSON-RPC
//    natif (jsonrpc/discussions.ts), en lecture seule ; « inconnu » tant qu'elles n'ont pas pu être lues ; « Ouvrir la
//    discussion » mène à la page de discussion (greffon acp-discussion), qui reprend la session et y rejoue la question.
// En tête : « À traiter par vous » (sections 1 à 5, questions « à vous » seulement) et « Chez Hermes ».
//
// Cible d'un lien profond (?vue=questions&q=<id> ou &carte=<tableau>/<carte>, correction K2) : la page fait défiler
// jusqu'à la demande et la marque (aria-current) ; une cible absente de la file le dit (« déjà traitée »), sauf si la
// page vient de la traiter elle-même, ou si son tableau est illisible (état inconnu, jamais « traitée »).
// Chaque message de réussite suit la RÉPONSE de l'API, jamais une supposition. Il est annoncé par la SECTION (relecture
// finale de P7) : la demande traitée quitte la file dès la relecture qui suit le geste (une question répondue n'est
// plus servie, une carte reprise quitte le triage), et un message porté par l'entrée disparaîtrait avec elle.
import type * as ReactTypes from "react";
import { T } from "../chaines";
import { BlocErreur, Carte, Donnee, EnChargement, Ligne } from "../commun";
import type { Lecture } from "../donnees";
import type { LectureDiscussions } from "../jsonrpc/discussions";
import { h, useEffect, useRef, useState, type Noeud } from "../react";
import { cheminDeBase } from "../sdk";
import { chaine, listeDeChaines } from "../types";
import {
  accepterRevue,
  conclureTriage,
  refuserRevue,
  relancerCarte,
  repondreQuestion,
  reprendreTriage,
} from "./api";
import { BlocRefus, Bouton, Etiquette, Horodatage, LienVue, RetourEnvoi, type Naviguer } from "./briques";
import { useEnvoi } from "./envoi";
import { libelleEtatQuestion, libelleStatut } from "./libelles";
import type {
  CarteEnAttente,
  ListeQuestions,
  QuestionOuverte,
  ResultatRelance,
  ResultatReponse,
  ResultatRevue,
  ResultatTriage,
  RevuePilotage,
} from "./types";

type Saisie = ReactTypes.ChangeEvent<HTMLTextAreaElement>;

/** Cible d'un lien profond : une question, ou une carte « tableau/carte ». */
export interface Cible {
  q?: string;
  carte?: string;
}

const cleCarte = (tableau: unknown, carte: unknown): string | null => {
  const t = chaine(tableau);
  const c = chaine(carte);
  return t && c ? `${t}/${c}` : null;
};

function LienProjet(props: { id: unknown; titre: unknown; naviguer: Naviguer }): Noeud {
  const id = chaine(props.id);
  const titre = <Donnee valeur={chaine(props.titre)} />;
  return id ? (
    <LienVue vue={{ genre: "detail", id }} naviguer={props.naviguer}>
      {titre}
    </LienVue>
  ) : (
    titre
  );
}

/** Élément de liste d'une demande, marqué s'il est la cible du lien profond. */
function Entree(props: { cible: boolean; classe?: string; children?: Noeud }): Noeud {
  const classes = ["acp-entree", props.classe, props.cible ? "acp-entree--cible" : null].filter(Boolean).join(" ");
  return (
    <li className={classes} aria-current={props.cible ? "true" : undefined} data-acp-cible={props.cible ? "" : undefined}>
      {props.children}
    </li>
  );
}

/** Message d'une section, tiré de la réponse de l'API ; ``alerte`` : le geste est enregistré mais la carte n'est pas
 *  repartie (le propriétaire a une suite à donner). ``statut`` : statut kanban rendu par l'API (relance). */
export interface Annonce {
  texte: string;
  alerte: boolean;
  statut?: string | null;
}

/** Annonce d'une section (``role="status"``) : garde le message quand l'entrée traitée quitte la file. */
function AnnonceSection(props: { annonce: Annonce | null }): Noeud {
  const { annonce } = props;
  if (!annonce) return null;
  return (
    <p className={annonce.alerte ? "acp-alerte-texte" : "acp-succes"} role="status">
      <span>{annonce.texte}</span>
      {annonce.statut ? (
        <span>
          {" "}
          <span>{T.projets.statutApres}</span> <Etiquette libelle={libelleStatut(annonce.statut)} brut={annonce.statut} />
        </span>
      ) : null}
    </p>
  );
}

/** Message de réussite d'une réponse, d'après la réponse de l'API (relecture de P4). */
export function messageReponse(resultat: ResultatReponse | null | undefined): string {
  if (resultat?.reprise_differee === true) return T.projets.reponseDifferee;
  if (resultat?.carte_debloquee === true) return T.projets.reponseEnvoyee;
  return T.projets.reponseSansReprise;
}

/** Annonce d'une réponse : alerte quand la carte n'a pas été relancée (ni reprise différée). */
export function annonceReponse(resultat: ResultatReponse | null | undefined): Annonce {
  const texte = messageReponse(resultat);
  return { texte, alerte: texte === T.projets.reponseSansReprise };
}

/** Message de réussite d'une décision sur une carte en triage, d'après la réponse de l'API. */
export function messageTriage(resultat: ResultatTriage | null | undefined): string {
  if (resultat?.reprise !== true) return T.projets.carteNonReprise;
  if (resultat.action === "prolongation") return T.projets.prolongationFaite;
  if (resultat.action === "relance_planification") return T.projets.relanceFaite;
  return T.projets.carteReprise;
}

/** Annonce d'une décision : alerte quand Hermes n'a pas repris la carte. */
export function annonceTriage(resultat: ResultatTriage | null | undefined): Annonce {
  const texte = messageTriage(resultat);
  return { texte, alerte: texte === T.projets.carteNonReprise };
}

/** Gestes d'une entrée : annoncer le message dans la section, marquer la cible traitée par la page, relire. */
interface Gestes {
  naviguer: Naviguer;
  apres: () => void;
  annoncer: (annonce: Annonce | null) => void;
  traitee: (cle: string) => void;
}

function QuiRepond(props: { question: QuestionOuverte }): Noeud {
  const { question } = props;
  if (question.chez === "hermes") {
    const statut = libelleStatut(question.carte_repondre_statut);
    return (
      <span className="acp-etat">
        <Etiquette libelle={{ texte: T.projets.chezHermes, famille: "actif" }} />
        {statut ? (
          <span className="acp-discret">
            <span>{T.projets.carteRepondre}</span> <Etiquette libelle={statut} />
          </span>
        ) : null}
      </span>
    );
  }
  if (question.chez === "proprietaire") return <Etiquette libelle={{ texte: T.projets.aVous, famille: "degrade" }} />;
  return <Donnee valeur={chaine(question.chez)} mono />;
}

function Question(props: { question: QuestionOuverte; cible: boolean } & Gestes): Noeud {
  const { question } = props;
  const id = chaine(question.id);
  const [reponse, fixerReponse] = useState("");
  const envoi = useEnvoi<ResultatReponse>();
  const champ = `acp-reponse-${id ?? "inconnue"}`;
  const repondre = async (evenement: ReactTypes.FormEvent) => {
    evenement.preventDefault();
    if (!id || !reponse.trim()) return;
    props.annoncer(null);
    const resultat = await envoi.envoyer(() => repondreQuestion(id, reponse.trim()));
    if (resultat !== null) {
      fixerReponse("");
      props.annoncer(annonceReponse(resultat));
      props.traitee(`q:${id}`);
      props.apres();
    }
  };
  return (
    <Entree cible={props.cible} classe="acp-question">
      <p className="acp-question__texte">
        <Donnee valeur={chaine(question.texte)} />
      </p>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.projet}>
          <LienProjet id={question.projet} titre={question.projet_titre} naviguer={props.naviguer} />
        </Ligne>
        <Ligne libelle={T.projets.etat}>
          <Etiquette libelle={libelleEtatQuestion(question.etat, question.chez)} brut={question.etat} />
        </Ligne>
        <Ligne libelle={T.projets.quiRepondQuestion}>
          <QuiRepond question={question} />
        </Ligne>
        {chaine(question.contexte) ? (
          <Ligne libelle={T.projets.contexte}>
            <Donnee valeur={chaine(question.contexte)} />
          </Ligne>
        ) : null}
        {chaine(question.motif_escalade) ? (
          <Ligne libelle={T.projets.motifEscalade}>
            <Donnee valeur={chaine(question.motif_escalade)} />
          </Ligne>
        ) : null}
        <Ligne libelle={T.projets.carteDeLaQuestion}>
          {chaine(question.carte_titre) ? (
            <span>
              <Donnee valeur={chaine(question.carte_titre)} />{" "}
              <span className="acp-discret">
                <Donnee valeur={chaine(question.carte)} mono />
              </span>
            </span>
          ) : (
            <Donnee valeur={chaine(question.carte)} mono />
          )}
        </Ligne>
        <Ligne libelle={T.projets.poseeLe}>
          <Horodatage valeur={question.cree_le} relative />
        </Ligne>
      </dl>
      {question.chez === "hermes" ? <p className="acp-discret">{T.projets.chezHermesAide}</p> : null}
      {id ? (
        <form className="acp-formulaire" onSubmit={(e: ReactTypes.FormEvent) => void repondre(e)}>
          <div className="acp-champ">
            <label htmlFor={champ}>{T.projets.votreReponse}</label>
            <textarea
              id={champ}
              data-acp-donnee=""
              rows={3}
              maxLength={4000}
              value={reponse}
              onChange={(e: Saisie) => fixerReponse(e.target.value)}
            />
          </div>
          <div className="acp-actions">
            <Bouton
              type="submit"
              principal
              libelle={T.projets.repondre}
              desactive={!reponse.trim() || envoi.etat.etat === "envoi"}
            />
          </div>
          <RetourEnvoi etat={envoi.etat} />
        </form>
      ) : null}
    </Entree>
  );
}

function Triage(props: { carte: CarteEnAttente; cible: boolean } & Gestes): Noeud {
  const { carte } = props;
  const tableau = chaine(carte.tableau);
  const identifiant = chaine(carte.carte);
  const actions = listeDeChaines(carte.actions);
  // Sans liste lisible, le geste historique : « Reprendre » (la route refuse ce qui ne s'applique pas).
  const gestes = actions.length > 0 ? actions : ["reprendre"];
  const avecConsigne = gestes.some((g) => g === "prolonger" || g === "relancer" || g === "reprendre");
  const [consigne, fixerConsigne] = useState("");
  const envoi = useEnvoi<ResultatTriage>();
  const conclusion = useEnvoi();
  const champ = `acp-consigne-${identifiant ?? "inconnue"}`;
  const reprendre = async (evenement: ReactTypes.FormEvent) => {
    evenement.preventDefault();
    if (!tableau || !identifiant) return;
    props.annoncer(null);
    const resultat = await envoi.envoyer(() => reprendreTriage(tableau, identifiant, consigne.trim() || null));
    if (resultat !== null) {
      fixerConsigne("");
      props.annoncer(annonceTriage(resultat));
      props.traitee(`carte:${tableau}/${identifiant}`);
      props.apres();
    }
  };
  const conclure = async () => {
    if (!tableau || !identifiant) return;
    props.annoncer(null);
    if ((await conclusion.envoyer(() => conclureTriage(tableau, identifiant))) !== null) {
      props.annoncer({ texte: T.projets.conclusionFaite, alerte: false });
      props.traitee(`carte:${tableau}/${identifiant}`);
      props.apres();
    }
  };
  const libelleReprise = gestes.includes("prolonger")
    ? T.projets.prolonger
    : gestes.includes("relancer")
      ? T.projets.relancer
      : T.projets.reprendreCarte;
  const aide =
    carte.genre === "tours"
      ? T.projets.prolongerAideTours
      : carte.genre === "cartes"
        ? T.projets.prolongerAideCartes
        : carte.genre === "sans_plan"
          ? T.projets.relancerAide
          : carte.genre === "corrections"
            ? T.projets.prolongerP6
            : null;
  const occupe = envoi.etat.etat === "envoi" || conclusion.etat.etat === "envoi";
  return (
    <Entree cible={props.cible}>
      <h3 className="acp-entree__nom">
        <Donnee valeur={chaine(carte.titre)} />
      </h3>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.projet}>
          <LienProjet id={carte.projet} titre={carte.projet_titre} naviguer={props.naviguer} />
        </Ligne>
        {chaine(carte.raison) ? (
          <Ligne libelle={T.projets.raison}>
            <Donnee valeur={chaine(carte.raison)} />
          </Ligne>
        ) : null}
      </dl>
      {aide ? <p className="acp-discret">{aide}</p> : null}
      {gestes.includes("conclure") ? <p className="acp-discret">{T.projets.conclureAide}</p> : null}
      {tableau && identifiant ? (
        <form className="acp-formulaire" onSubmit={(e: ReactTypes.FormEvent) => void reprendre(e)}>
          {avecConsigne ? (
            <div className="acp-champ">
              <label htmlFor={champ}>{T.projets.consigne}</label>
              <textarea
                id={champ}
                data-acp-donnee=""
                rows={3}
                maxLength={8000}
                value={consigne}
                onChange={(e: Saisie) => fixerConsigne(e.target.value)}
              />
            </div>
          ) : null}
          <div className="acp-actions">
            {avecConsigne ? <Bouton type="submit" principal libelle={libelleReprise} desactive={occupe} /> : null}
            {gestes.includes("conclure") ? (
              <Bouton libelle={T.projets.conclure} surClic={() => void conclure()} desactive={occupe} />
            ) : null}
          </div>
          <RetourEnvoi etat={envoi.etat} />
          <RetourEnvoi etat={conclusion.etat} />
        </form>
      ) : null}
    </Entree>
  );
}

/** Une revue de fichiers de pilotage. Le message de réussite est annoncé par la section (``annoncer``) : la revue
 *  quitte la liste dès le rechargement, et son propre message disparaîtrait avec elle. */
function Revue(props: { revue: RevuePilotage; cible: boolean } & Gestes): Noeud {
  const { revue } = props;
  const tableau = chaine(revue.tableau);
  const identifiant = chaine(revue.carte);
  const chemins = listeDeChaines(revue.chemins);
  const [motif, fixerMotif] = useState("");
  const acceptation = useEnvoi<ResultatRevue>();
  const refus = useEnvoi<ResultatRevue>();
  const champ = `acp-motif-revue-${identifiant ?? "inconnue"}`;
  const accepter = async () => {
    if (!tableau || !identifiant) return;
    props.annoncer(null);
    if ((await acceptation.envoyer(() => accepterRevue(tableau, identifiant))) !== null) {
      props.annoncer({ texte: T.projets.revueAcceptee, alerte: false });
      props.traitee(`carte:${tableau}/${identifiant}`);
      props.apres();
    }
  };
  const refuser = async (evenement: ReactTypes.FormEvent) => {
    evenement.preventDefault();
    if (!tableau || !identifiant || !motif.trim()) return;
    props.annoncer(null);
    if ((await refus.envoyer(() => refuserRevue(tableau, identifiant, motif.trim()))) !== null) {
      fixerMotif("");
      props.annoncer({ texte: T.projets.revueRefusee, alerte: false });
      props.traitee(`carte:${tableau}/${identifiant}`);
      props.apres();
    }
  };
  const d = revue.diffstat;
  const occupe = acceptation.etat.etat === "envoi" || refus.etat.etat === "envoi";
  return (
    <Entree cible={props.cible}>
      <h3 className="acp-entree__nom">
        <Donnee valeur={chaine(revue.titre)} />
      </h3>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.projet}>
          <LienProjet id={revue.projet} titre={revue.projet_titre} naviguer={props.naviguer} />
        </Ligne>
        <Ligne libelle={T.projets.chemins}>
          {chemins.length === 0 ? (
            <Donnee valeur={null} />
          ) : (
            <ul className="acp-noms">
              {chemins.map((c) => (
                <li key={c}>
                  <Donnee valeur={c} mono />
                </li>
              ))}
            </ul>
          )}
        </Ligne>
        <Ligne libelle={T.projets.diffstat}>
          {d ? (
            <span className="acp-etat">
              <span>
                <Donnee valeur={d.fichiers ?? null} /> {T.projets.fichiers}
              </span>
              <span>
                <Donnee valeur={d.ajouts ?? null} /> {T.projets.ajouts}
              </span>
              <span>
                <Donnee valeur={d.retraits ?? null} /> {T.projets.retraits}
              </span>
            </span>
          ) : (
            <Donnee valeur={null} />
          )}
        </Ligne>
        <Ligne libelle={T.projets.branche}>
          <Donnee valeur={chaine(revue.branche)} mono />
        </Ligne>
        <Ligne libelle={T.projets.tete}>
          <Donnee valeur={chaine(revue.tete)} mono />
        </Ligne>
        <Ligne libelle={T.projets.resume}>
          <Donnee valeur={chaine(revue.resume)} />
        </Ligne>
      </dl>
      <p className="acp-discret">
        <Donnee valeur={chaine(revue.diff)} />
      </p>
      {tableau && identifiant ? (
        <form className="acp-formulaire" onSubmit={(e: ReactTypes.FormEvent) => void refuser(e)}>
          <div className="acp-champ">
            <label htmlFor={champ}>{T.projets.motifRefus}</label>
            <textarea
              id={champ}
              data-acp-donnee=""
              rows={2}
              maxLength={1000}
              value={motif}
              onChange={(e: Saisie) => fixerMotif(e.target.value)}
            />
          </div>
          <div className="acp-actions">
            <Bouton principal libelle={T.projets.accepterRevue} surClic={() => void accepter()} desactive={occupe} />
            <Bouton type="submit" danger libelle={T.projets.refuserRevue} desactive={occupe || !motif.trim()} />
          </div>
          <RetourEnvoi etat={acceptation.etat} />
          <RetourEnvoi etat={refus.etat} />
        </form>
      ) : null}
    </Entree>
  );
}

/** Message d'une relance, d'après la réponse de l'API (cahier P7 § 3.4) ; ``integration`` : la carte relancée est une
 *  carte d'intégration, sans agent (relecture finale de P7) — elle rejoue la même fusion, jamais une « session neuve ». */
export function messageRelance(resultat: ResultatRelance | null | undefined, integration = false): string {
  if (resultat?.relancee === true) {
    // Partie E (K25) : carte bloquée pour un secret, repartie sur une branche neuve sans le travail en quarantaine.
    if (resultat.branche_neuve === true) return T.projets.relanceeBrancheNeuve;
    if (integration) return T.projets.relanceeFusion;
    return resultat.session_neuve === true ? T.projets.relanceeSessionNeuve : T.projets.relancee;
  }
  return T.projets.nonRelancee;
}

/** Une carte arrêtée (bloquée ou abandonnée) : « Relancer » avec une consigne facultative, ou la raison du refus. Le
 *  message de la relance est annoncé par la section : la carte quitte la liste dès le rechargement. Une carte
 *  d'intégration n'a pas d'agent : ni consigne, ni « session neuve » (la relance rejoue la même fusion). */
function Arretee(props: { carte: CarteEnAttente; cible: boolean } & Gestes): Noeud {
  const { carte } = props;
  const tableau = chaine(carte.tableau);
  const identifiant = chaine(carte.carte);
  const [consigne, fixerConsigne] = useState("");
  const envoi = useEnvoi<ResultatRelance>();
  const champ = `acp-relance-${identifiant ?? "inconnue"}`;
  const integration = carte.integration === true;
  const relancer = async (evenement: ReactTypes.FormEvent) => {
    evenement.preventDefault();
    if (!tableau || !identifiant) return;
    props.annoncer(null);
    const envoyee = integration ? null : consigne.trim() || null;
    const resultat = await envoi.envoyer(() => relancerCarte(tableau, identifiant, envoyee));
    if (resultat !== null) {
      fixerConsigne("");
      const texte = messageRelance(resultat, integration);
      props.annoncer({ texte, alerte: texte === T.projets.nonRelancee, statut: chaine(resultat.statut_apres) });
      props.traitee(`carte:${tableau}/${identifiant}`);
      props.apres();
    }
  };
  return (
    <Entree cible={props.cible}>
      <h3 className="acp-entree__nom">
        <Donnee valeur={chaine(carte.titre)} />
      </h3>
      <p className="acp-etat">
        {carte.abandonnee === true ? (
          <Etiquette libelle={{ texte: T.projets.abandonnee, famille: "echec" }} />
        ) : (
          <Etiquette libelle={{ texte: T.projets.statuts.blocked, famille: "echec" }} />
        )}
      </p>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.projet}>
          <LienProjet id={carte.projet} titre={carte.projet_titre} naviguer={props.naviguer} />
        </Ligne>
        <Ligne libelle={T.projets.assigne}>
          <Donnee valeur={chaine(carte.assigne)} mono />
        </Ligne>
        <Ligne libelle={T.projets.raison}>
          <Donnee valeur={chaine(carte.raison)} />
        </Ligne>
      </dl>
      {carte.relancable === true && tableau && identifiant ? (
        <form className="acp-formulaire" onSubmit={(e: ReactTypes.FormEvent) => void relancer(e)}>
          {carte.quarantaine === true ? (
            <p className="acp-alerte-texte">{T.projets.relanceQuarantaineAide}</p>
          ) : integration ? (
            <p className="acp-discret">{T.projets.relanceIntegrationAide}</p>
          ) : carte.executant === true ? (
            <p className="acp-discret">{T.projets.relanceExecutantAide}</p>
          ) : null}
          {integration ? null : (
            <div className="acp-champ">
              <label htmlFor={champ}>{T.projets.consigne}</label>
              <textarea
                id={champ}
                data-acp-donnee=""
                rows={3}
                maxLength={4000}
                value={consigne}
                onChange={(e: Saisie) => fixerConsigne(e.target.value)}
              />
            </div>
          )}
          <div className="acp-actions">
            <Bouton type="submit" principal libelle={T.projets.relancerCarte} desactive={envoi.etat.etat === "envoi"} />
          </div>
          <RetourEnvoi etat={envoi.etat} />
        </form>
      ) : (
        <p className="acp-discret">
          <span>{T.projets.nonRelancable}</span> <Donnee valeur={chaine(carte.refus_relance)} />
        </p>
      )}
    </Entree>
  );
}

function Discussions(props: { lecture: Lecture<LectureDiscussions>; serveur: ListeQuestions["discussions"] }): Noeud {
  const valeur = props.lecture.valeur;
  let contenu: Noeud;
  if (valeur === null) {
    contenu = props.lecture.erreur ? <p className="acp-discret">{T.projets.discussionsInconnues}</p> : <EnChargement />;
  } else if (!valeur.connu) {
    const requetes = props.serveur?.suivies === true ? props.serveur.requetes_ouvertes : null;
    contenu = (
      <div>
        <p className="acp-discret">{T.projets.discussionsInconnues}</p>
        {typeof requetes === "number" ? (
          <p className="acp-discret">
            <span>{T.projets.requetesOuvertes}</span> <Donnee valeur={requetes} />
          </p>
        ) : null}
      </div>
    );
  } else if (valeur.sessions.length === 0) {
    contenu = <p className="acp-discret">{T.projets.aucuneDiscussion}</p>;
  } else {
    contenu = (
      <ul className="acp-entrees acp-entrees--une">
        {valeur.sessions.map((s) => (
          <li key={s.cle} className="acp-entree">
            <h3 className="acp-entree__nom">
              {s.titre ? <Donnee valeur={s.titre} /> : <span>{T.projets.discussionSansTitre}</span>}
            </h3>
            <dl className="acp-liste">
              <Ligne libelle={T.projets.discussionEtat}>
                <Etiquette libelle={{ texte: T.projets.discussionEnAttente, famille: "degrade" }} />
              </Ligne>
              <Ligne libelle={T.projets.discussionActivite}>
                <Horodatage valeur={s.derniereActivite} relative />
              </Ligne>
              <Ligne libelle={T.projets.discussionApercu}>
                <Donnee valeur={s.apercu} />
              </Ligne>
              <Ligne libelle={T.projets.discussionCle}>
                <Donnee valeur={s.cle} mono />
              </Ligne>
            </dl>
            <div className="acp-actions">
              {/* Étape P7, part D : la page de discussion reprend la session et y rejoue la question (open_requests). */}
              <a className="acp-bouton acp-bouton--principal"
                 href={`${cheminDeBase()}/discussion?session=${encodeURIComponent(s.cle)}`}>
                {T.discussion.ouvrirDiscussion}
              </a>
            </div>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <Carte titre={T.projets.discussionsTitre} id="acp-questions-discussions">
      <p className="acp-discret">{T.projets.discussionsIntro}</p>
      {contenu}
      <p className="acp-discret">{T.projets.discussionsLimite}</p>
    </Carte>
  );
}

/** « À traiter par vous » : compteurs du greffon plus les discussions en attente lues par le client ; ``null`` tant
 *  que la file n'est pas lue. ``discussionsConnues`` faux : le total ne compte pas les discussions, et la page le dit. */
export function aTraiter(
  file: ListeQuestions | null,
  discussions: LectureDiscussions | null,
): { total: number; chezHermes: number | null; discussionsConnues: boolean } | null {
  const compteurs = file?.compteurs;
  if (!compteurs || typeof compteurs.a_traiter !== "number") return null;
  const connues = discussions !== null && discussions.connu;
  return {
    total: compteurs.a_traiter + (connues ? discussions.sessions.length : 0),
    chezHermes: typeof compteurs.chez_hermes === "number" ? compteurs.chez_hermes : null,
    discussionsConnues: connues,
  };
}

function Resume(props: { file: ListeQuestions; discussions: LectureDiscussions | null }): Noeud {
  const compte = aTraiter(props.file, props.discussions);
  if (compte === null) return null;
  return (
    <section className="acp-carte" aria-labelledby="acp-questions-resume">
      <h2 className="acp-carte__titre" id="acp-questions-resume">
        {T.projets.fileTitre}
      </h2>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.aTraiterParVous}>
          <span>
            <Donnee valeur={compte.total} />
            {compte.discussionsConnues ? null : <span className="acp-discret"> {T.projets.discussionsNonComptees}</span>}
          </span>
        </Ligne>
        <Ligne libelle={T.projets.chezHermesCompte}>
          <Donnee valeur={compte.chezHermes} />
        </Ligne>
      </dl>
    </section>
  );
}

export function Questions(props: {
  lecture: Lecture<ListeQuestions>;
  discussions: Lecture<LectureDiscussions>;
  cible: Cible;
  naviguer: Naviguer;
  apres: () => void;
}): Noeud {
  const [annonceQuestion, fixerAnnonceQuestion] = useState<Annonce | null>(null);
  const [annonceTriage, fixerAnnonceTriage] = useState<Annonce | null>(null);
  const [annonceRevue, fixerAnnonceRevue] = useState<Annonce | null>(null);
  const [annonceRelance, fixerAnnonceRelance] = useState<Annonce | null>(null);
  // Demandes traitées par un geste de CETTE page (« q:<id> », « carte:<tableau>/<carte> ») : leur sortie de la file
  // n'est pas « déjà traitée » ; le message de l'API est annoncé par la section.
  const [traitees, fixerTraitees] = useState<string[]>([]);
  const traitee = (cle: string) => fixerTraitees((avant) => (avant.includes(cle) ? avant : [...avant, cle]));
  const defile = useRef<string | null>(null);
  const donnees = props.lecture.valeur;
  const questions = Array.isArray(donnees?.questions) ? donnees.questions : [];
  const triage = Array.isArray(donnees?.triage) ? donnees.triage : [];
  const bloquees = Array.isArray(donnees?.bloquees) ? donnees.bloquees : [];
  const revues = Array.isArray(donnees?.revues) ? donnees.revues : [];
  const illisibles = listeDeChaines(donnees?.tableaux_illisibles);
  const estQuestion = (q: QuestionOuverte) => Boolean(props.cible.q) && chaine(q.id) === props.cible.q;
  const estCarte = (c: { tableau?: unknown; carte?: unknown }) =>
    Boolean(props.cible.carte) && cleCarte(c.tableau, c.carte) === props.cible.carte;
  const cibleVoulue = props.cible.q ? `q:${props.cible.q}` : props.cible.carte ? `carte:${props.cible.carte}` : null;
  const cibleTrouvee =
    questions.some(estQuestion) || triage.some(estCarte) || revues.some(estCarte) || bloquees.some(estCarte);
  const cibleTraiteeIci = cibleVoulue !== null && traitees.includes(cibleVoulue);
  // Carte d'un tableau que le greffon n'a pas pu lire : son état est inconnu, elle n'est pas « déjà traitée ».
  const tableauCible = props.cible.carte ? props.cible.carte.split("/")[0] : null;
  const cibleIllisible = tableauCible !== null && illisibles.includes(tableauCible);
  // Défilement jusqu'à la cible, UNE fois par cible (une actualisation ne ramène pas la page sur elle).
  useEffect(() => {
    if (!cibleVoulue || !cibleTrouvee || defile.current === cibleVoulue) return;
    defile.current = cibleVoulue;
    try {
      document.querySelector("[data-acp-cible]")?.scrollIntoView?.({ block: "center" });
    } catch {
      // Défilement impossible : la cible reste marquée.
    }
  }, [cibleVoulue, cibleTrouvee]);
  if (donnees === null) {
    return props.lecture.erreur ? (
      <BlocErreur erreur={props.lecture.erreur} message={T.projets.questionsIndisponibles} />
    ) : (
      <EnChargement />
    );
  }
  return (
    <div className="acp-sections">
      {props.lecture.erreur ? <BlocRefus erreur={props.lecture.erreur} /> : null}
      {cibleVoulue && !cibleTrouvee && !cibleTraiteeIci ? (
        <p className="acp-alerte-texte" role="status">
          {cibleIllisible ? T.projets.cibleIllisible : T.projets.cibleTraitee}
        </p>
      ) : null}
      <Resume file={donnees} discussions={props.discussions.valeur} />
      <Carte titre={T.projets.questionsTitre} id="acp-questions-ouvertes">
        <AnnonceSection annonce={annonceQuestion} />
        {questions.length === 0 ? (
          <p className="acp-discret">{T.projets.aucuneQuestion}</p>
        ) : (
          <ul className="acp-entrees acp-entrees--une">
            {questions.map((q, rang) => (
              <Question
                key={chaine(q.id) ?? String(rang)}
                question={q}
                cible={estQuestion(q)}
                naviguer={props.naviguer}
                apres={props.apres}
                annoncer={fixerAnnonceQuestion}
                traitee={traitee}
              />
            ))}
          </ul>
        )}
      </Carte>
      <Carte titre={T.projets.triageTitre} id="acp-questions-triage">
        <AnnonceSection annonce={annonceTriage} />
        {triage.length === 0 ? (
          <p className="acp-discret">{T.projets.aucunTriage}</p>
        ) : (
          <ul className="acp-entrees acp-entrees--une">
            {triage.map((c, rang) => (
              <Triage
                key={chaine(c.carte) ?? String(rang)}
                carte={c}
                cible={estCarte(c)}
                naviguer={props.naviguer}
                apres={props.apres}
                annoncer={fixerAnnonceTriage}
                traitee={traitee}
              />
            ))}
          </ul>
        )}
      </Carte>
      <Carte titre={T.projets.revuesTitre} id="acp-questions-revues">
        <p className="acp-discret">{T.projets.revuesIntro}</p>
        <AnnonceSection annonce={annonceRevue} />
        {revues.length === 0 ? (
          <p className="acp-discret">{T.projets.aucuneRevue}</p>
        ) : (
          <ul className="acp-entrees acp-entrees--une">
            {revues.map((r, rang) => (
              <Revue
                key={chaine(r.carte) ?? String(rang)}
                revue={r}
                cible={estCarte(r)}
                naviguer={props.naviguer}
                apres={props.apres}
                annoncer={fixerAnnonceRevue}
                traitee={traitee}
              />
            ))}
          </ul>
        )}
      </Carte>
      <Carte titre={T.projets.bloqueesTitre} id="acp-questions-bloquees">
        <p className="acp-discret">{T.projets.bloqueesIntro}</p>
        <AnnonceSection annonce={annonceRelance} />
        {bloquees.length === 0 ? (
          <p className="acp-discret">{T.projets.aucuneBloquee}</p>
        ) : (
          <ul className="acp-entrees">
            {bloquees.map((c, rang) => (
              <Arretee
                key={chaine(c.carte) ?? String(rang)}
                carte={c}
                cible={estCarte(c)}
                naviguer={props.naviguer}
                apres={props.apres}
                annoncer={fixerAnnonceRelance}
                traitee={traitee}
              />
            ))}
          </ul>
        )}
      </Carte>
      <Discussions lecture={props.discussions} serveur={donnees.discussions} />
      {illisibles.length > 0 ? (
        <Carte titre={T.projets.tableauxIllisibles} id="acp-questions-illisibles">
          <ul className="acp-noms">
            {illisibles.map((t) => (
              <li key={t}>
                <Donnee valeur={t} mono />
              </li>
            ))}
          </ul>
        </Carte>
      ) : null}
    </div>
  );
}
