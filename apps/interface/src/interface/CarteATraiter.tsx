// Carte « À traiter par vous » de l'Accueil (cahier P7 § 8.3, bloc 1) : le compte (questions à vous, décisions,
// revues, cartes arrêtées, et les discussions en attente quand elles ont pu être lues), les trois premières demandes
// (liens profonds vers la file Questions, en paramètres de requête) et « Chez Hermes ». Bloc illisible : sa raison.
// Discussions en attente non lues (en cours de lecture, ou inconnues) : le total le dit, comme la file Questions, et
// « Rien n'attend votre décision. » n'est jamais affiché (relecture finale de P7 : jamais zéro par défaut).
import { T } from "../chaines";
import { Carte, Donnee, Ligne, Lien } from "../commun";
import type { LectureDiscussions } from "../jsonrpc/discussions";
import { h, type Noeud } from "../react";
import { chaine } from "../types";
import type { ATraiterAccueil } from "./accueil-api";

const CIBLE = /^\/projets\?vue=questions(&(q|carte)=[A-Za-z0-9_\-/%]+)?$/;

function libelleGenre(genre: unknown): string | null {
  switch (genre) {
    case "question":
      return T.accueil.genreQuestion;
    case "decision":
      return T.accueil.genreDecision;
    case "revue":
      return T.accueil.genreRevue;
    case "arretee":
      return T.accueil.genreArretee;
    default:
      return null;
  }
}

export function CarteATraiter(props: {
  aTraiter: ATraiterAccueil | null | undefined;
  chezHermes: number | null | undefined;
  discussions: LectureDiscussions | null;
  illisible: string | null;
}): Noeud {
  const bloc = props.aTraiter ?? null;
  const connues = props.discussions !== null && props.discussions.connu;
  const nbDiscussions = connues && props.discussions?.connu ? props.discussions.sessions.length : null;
  const total = bloc && typeof bloc.total === "number" ? bloc.total + (nbDiscussions ?? 0) : null;
  const premieres = Array.isArray(bloc?.premieres) ? bloc.premieres : [];
  return (
    <Carte titre={T.accueil.aTraiterTitre} id="acp-accueil-a-traiter">
      {bloc === null ? (
        <p className="acp-alerte-texte">
          <span>{T.accueil.blocIllisible}</span> <Donnee valeur={props.illisible} />
        </p>
      ) : (
        <div className="acp-sections">
          <p className="acp-chiffre">
            <Donnee valeur={total} />
            {nbDiscussions === null ? <span className="acp-discret"> {T.projets.discussionsNonComptees}</span> : null}
          </p>
          <dl className="acp-liste">
            <Ligne libelle={T.accueil.questions}>
              <Donnee valeur={bloc.questions ?? null} />
            </Ligne>
            <Ligne libelle={T.accueil.decisions}>
              <Donnee valeur={bloc.decisions ?? null} />
            </Ligne>
            <Ligne libelle={T.accueil.revues}>
              <Donnee valeur={bloc.revues ?? null} />
            </Ligne>
            <Ligne libelle={T.accueil.arretees}>
              <Donnee valeur={bloc.arretees ?? null} />
            </Ligne>
            <Ligne libelle={T.accueil.discussionsEnAttente}>
              {nbDiscussions === null ? <span>{T.accueil.inconnues}</span> : <Donnee valeur={nbDiscussions} />}
            </Ligne>
            <Ligne libelle={T.accueil.chezHermes}>
              <Donnee valeur={typeof props.chezHermes === "number" ? props.chezHermes : null} />
            </Ligne>
          </dl>
          {premieres.length > 0 ? (
            <ul className="acp-noms">
              {premieres.map((d, rang) => {
                const cible = chaine(d.cible);
                const genre = libelleGenre(d.genre);
                return (
                  <li key={`${cible ?? rang}`}>
                    {genre ? <span className="acp-discret">{genre} </span> : null}
                    {cible && CIBLE.test(cible) ? (
                      <Lien vers={cible}>
                        <Donnee valeur={chaine(d.titre)} />
                      </Lien>
                    ) : (
                      <Donnee valeur={chaine(d.titre)} />
                    )}{" "}
                    <span className="acp-discret">
                      <Donnee valeur={chaine(d.projet_titre)} />
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : total === 0 && nbDiscussions !== null ? (
            <p className="acp-discret">{T.accueil.rienATraiter}</p>
          ) : null}
        </div>
      )}
      <p>
        <Lien vers="/projets?vue=questions">{T.accueil.ouvrirQuestions}</Lien>
      </p>
    </Carte>
  );
}
