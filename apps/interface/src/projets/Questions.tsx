// Vue « Questions » (GET /v1/questions) :
// - questions ouvertes ou escaladées : texte, contexte, projet, carte (titre), et une réponse du propriétaire
//   (POST /v1/questions/{q}/reponse : commentaire sur la carte, puis reprise — différée si le projet est en
//   pause) ; le message de réussite suit la RÉPONSE de l'API, jamais une supposition ;
// - cartes en triage : les gestes que le greffon offre (« Prolonger » ou « Relancer la planification » avec
//   une consigne facultative, « Conclure le projet » ; « Reprendre » pour une autre carte en triage) ;
// - cartes bloquées ou abandonnées : LECTURE SEULE en P4 (« Relancer » relève de P7 : aucun bouton), avec
//   leur raison connue.
import type * as ReactTypes from "react";
import { T } from "../chaines";
import { BlocErreur, Carte, Donnee, EnChargement, Ligne } from "../commun";
import { h, useState, type Noeud } from "../react";
import { chaine, listeDeChaines } from "../types";
import { conclureTriage, lireQuestions, repondreQuestion, reprendreTriage } from "./api";
import { BlocRefus, Bouton, Etiquette, Horodatage, LienVue, RetourEnvoi, type Naviguer } from "./briques";
import { useEnvoi } from "./envoi";
import { libelleEtatQuestion } from "./libelles";
import { useSondage } from "./sondage";
import type { CarteEnAttente, ListeQuestions, QuestionOuverte, ResultatReponse, ResultatTriage } from "./types";

type Saisie = ReactTypes.ChangeEvent<HTMLTextAreaElement>;

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

/** Message de réussite d'une réponse, d'après la réponse de l'API (relecture de P4). */
export function messageReponse(resultat: ResultatReponse | null | undefined): string {
  if (resultat?.reprise_differee === true) return T.projets.reponseDifferee;
  if (resultat?.carte_debloquee === true) return T.projets.reponseEnvoyee;
  return T.projets.reponseSansReprise;
}

/** Message de réussite d'une décision sur une carte en triage, d'après la réponse de l'API. */
export function messageTriage(resultat: ResultatTriage | null | undefined): string {
  if (resultat?.reprise !== true) return T.projets.carteNonReprise;
  if (resultat.action === "prolongation") return T.projets.prolongationFaite;
  if (resultat.action === "relance_planification") return T.projets.relanceFaite;
  return T.projets.carteReprise;
}

function Question(props: { question: QuestionOuverte; naviguer: Naviguer; apres: () => void }): Noeud {
  const { question } = props;
  const id = chaine(question.id);
  const [reponse, fixerReponse] = useState("");
  const envoi = useEnvoi<ResultatReponse>();
  const champ = `acp-reponse-${id ?? "inconnue"}`;
  const repondre = async (evenement: ReactTypes.FormEvent) => {
    evenement.preventDefault();
    if (!id || !reponse.trim()) return;
    if ((await envoi.envoyer(() => repondreQuestion(id, reponse.trim()))) !== null) {
      fixerReponse("");
      props.apres();
    }
  };
  return (
    <li className="acp-entree acp-question">
      <p className="acp-question__texte">
        <Donnee valeur={chaine(question.texte)} />
      </p>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.projet}>
          <LienProjet id={question.projet} titre={question.projet_titre} naviguer={props.naviguer} />
        </Ligne>
        <Ligne libelle={T.projets.etat}>
          <Etiquette libelle={libelleEtatQuestion(question.etat)} brut={question.etat} />
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
          <RetourEnvoi
            etat={envoi.etat}
            reussite={envoi.etat.etat === "ok" ? messageReponse(envoi.etat.resultat) : undefined}
          />
        </form>
      ) : null}
    </li>
  );
}

function Triage(props: { carte: CarteEnAttente; naviguer: Naviguer; apres: () => void }): Noeud {
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
    if ((await envoi.envoyer(() => reprendreTriage(tableau, identifiant, consigne.trim() || null))) !== null) {
      fixerConsigne("");
      props.apres();
    }
  };
  const conclure = async () => {
    if (!tableau || !identifiant) return;
    if ((await conclusion.envoyer(() => conclureTriage(tableau, identifiant))) !== null) props.apres();
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
    <li className="acp-entree">
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
          <RetourEnvoi
            etat={envoi.etat}
            reussite={envoi.etat.etat === "ok" ? messageTriage(envoi.etat.resultat) : undefined}
          />
          <RetourEnvoi etat={conclusion.etat} reussite={T.projets.conclusionFaite} />
        </form>
      ) : null}
    </li>
  );
}

function Bloquee(props: { carte: CarteEnAttente; naviguer: Naviguer }): Noeud {
  const { carte } = props;
  return (
    <li className="acp-entree">
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
    </li>
  );
}

export function Questions(props: { jeton: number; naviguer: Naviguer; apres: () => void }): Noeud {
  const sondage = useSondage<ListeQuestions>(lireQuestions, props.jeton);
  const donnees = sondage.valeur;
  if (donnees === null) {
    return sondage.erreur ? <BlocErreur erreur={sondage.erreur} message={T.projets.questionsIndisponibles} /> : <EnChargement />;
  }
  const questions = Array.isArray(donnees.questions) ? donnees.questions : [];
  const triage = Array.isArray(donnees.triage) ? donnees.triage : [];
  const bloquees = Array.isArray(donnees.bloquees) ? donnees.bloquees : [];
  const illisibles = listeDeChaines(donnees.tableaux_illisibles);
  return (
    <div className="acp-sections">
      {sondage.erreur ? <BlocRefus erreur={sondage.erreur} /> : null}
      <Carte titre={T.projets.questionsTitre} id="acp-questions-ouvertes">
        {questions.length === 0 ? (
          <p className="acp-discret">{T.projets.aucuneQuestion}</p>
        ) : (
          <ul className="acp-entrees acp-entrees--une">
            {questions.map((q, rang) => (
              <Question key={chaine(q.id) ?? String(rang)} question={q} naviguer={props.naviguer} apres={props.apres} />
            ))}
          </ul>
        )}
      </Carte>
      <Carte titre={T.projets.triageTitre} id="acp-questions-triage">
        {triage.length === 0 ? (
          <p className="acp-discret">{T.projets.aucunTriage}</p>
        ) : (
          <ul className="acp-entrees acp-entrees--une">
            {triage.map((c, rang) => (
              <Triage key={chaine(c.carte) ?? String(rang)} carte={c} naviguer={props.naviguer} apres={props.apres} />
            ))}
          </ul>
        )}
      </Carte>
      <Carte titre={T.projets.bloqueesTitre} id="acp-questions-bloquees">
        <p className="acp-discret">{T.projets.bloqueesNote}</p>
        {bloquees.length === 0 ? (
          <p className="acp-discret">{T.projets.aucuneBloquee}</p>
        ) : (
          <ul className="acp-entrees">
            {bloquees.map((c, rang) => (
              <Bloquee key={chaine(c.carte) ?? String(rang)} carte={c} naviguer={props.naviguer} />
            ))}
          </ul>
        )}
      </Carte>
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
