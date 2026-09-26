// Vue « détail » d'un projet (GET /v1/projets/{id}) : état, tour et plafonds, cartes groupées par rôle
// (statut, exécutant, modèle demandé, effort, palier, « Modèle servi : Non observé » avant P6, résumé
// replié), tours et décisions, questions en attente, journal ; « Mettre en pause » et « Reprendre »
// appellent les routes réelles.
import { T } from "../chaines";
import { Carte, Donnee, EnChargement, Ligne } from "../commun";
import { nombre } from "../format";
import { h, type Noeud } from "../react";
import { chaine, listeDeChaines } from "../types";
import { lireProjet, pauseProjet, repriseProjet } from "./api";
import { BlocRefus, Bouton, EtatDuPoste, Etiquette, Horodatage, LienVue, RetourEnvoi, type Naviguer } from "./briques";
import { useEnvoi } from "./envoi";
import {
  libelleEtatProjet,
  libelleEtatQuestion,
  libelleOrigine,
  libelleProfil,
  libelleReponses,
  libelleRole,
  libelleStatut,
  libelleVoie,
  ORDRE_DES_ROLES,
} from "./libelles";
import { Avancement } from "./ListeProjets";
import { useSondage } from "./sondage";
import type { CarteProjet, DetailProjet as Detail, ListeProjets, ReponseDetail } from "./types";

function Libre(props: { texte: string | null; brut: unknown; mono?: boolean }): Noeud {
  return props.texte ? <span>{props.texte}</span> : <Donnee valeur={chaine(props.brut)} mono={props.mono} />;
}

function EnTete(props: { projet: Detail; liste: ListeProjets | null; apres: () => void }): Noeud {
  const { projet } = props;
  const id = chaine(projet.id);
  const envoi = useEnvoi();
  const geste = async (travail: () => Promise<unknown>) => {
    if ((await envoi.envoyer(travail)) !== null) props.apres();
  };
  const plafonds = projet.plafonds ?? {};
  return (
    <section className="acp-carte" aria-labelledby="acp-projet-titre">
      <h2 className="acp-carte__titre acp-carte__titre--grand" id="acp-projet-titre">
        <Donnee valeur={chaine(projet.titre)} />
      </h2>
      <p className="acp-etat">
        <Etiquette libelle={libelleEtatProjet(projet.etat, projet.etat_derive)} brut={projet.etat} />
      </p>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.objectif}>
          <Donnee valeur={chaine(projet.objectif)} />
        </Ligne>
        <Ligne libelle={T.projets.cartesFaites}>
          <Avancement faites={projet.compteurs?.faites} total={projet.compteurs?.total} />
        </Ligne>
        <Ligne libelle={T.projets.tour}>
          <Donnee valeur={nombre(projet.tour)} /> <span className="acp-discret">{T.projets.sur}</span>{" "}
          <Donnee valeur={nombre(plafonds.tours)} />
        </Ligne>
        <Ligne libelle={T.projets.cartesCreees}>
          <Donnee valeur={nombre(projet.cartes_creees)} /> <span className="acp-discret">{T.projets.sur}</span>{" "}
          <Donnee valeur={nombre(plafonds.cartes)} />
        </Ligne>
        <Ligne libelle={T.projets.correctionsParEtape}>
          <Donnee valeur={nombre(plafonds.corrections)} />
        </Ligne>
        <Ligne libelle={T.projets.profil}>
          <Libre texte={libelleProfil(projet.profil)} brut={projet.profil} mono />
        </Ligne>
        <Ligne libelle={T.projets.depot}>
          {projet.depot === null ? <span>{T.projets.sansDepot}</span> : <Donnee valeur={chaine(projet.depot)} mono />}
        </Ligne>
        <Ligne libelle={T.projets.reponses}>
          <Libre texte={libelleReponses(projet.reponses)} brut={projet.reponses} mono />
        </Ligne>
        <Ligne libelle={T.projets.poste}>
          <EtatDuPoste poste={props.liste?.poste} />
        </Ligne>
        <Ligne libelle={T.projets.origine}>
          <Libre texte={libelleOrigine(projet.origine)} brut={projet.origine} mono />
        </Ligne>
        <Ligne libelle={T.projets.creeLe}>
          <Horodatage valeur={projet.cree_le} />
        </Ligne>
        {projet.termine_le ? (
          <Ligne libelle={T.projets.termineLe}>
            <Horodatage valeur={projet.termine_le} />
          </Ligne>
        ) : null}
      </dl>
      {id && (projet.etat === "actif" || projet.etat === "en_pause") ? (
        <div className="acp-actions">
          {projet.etat === "actif" ? (
            <Bouton
              libelle={T.projets.mettreEnPause}
              desactive={envoi.etat.etat === "envoi"}
              surClic={() => void geste(() => pauseProjet(id))}
            />
          ) : (
            <Bouton
              libelle={T.projets.reprendre}
              principal
              desactive={envoi.etat.etat === "envoi"}
              surClic={() => void geste(() => repriseProjet(id))}
            />
          )}
        </div>
      ) : null}
      <RetourEnvoi etat={envoi.etat} />
    </section>
  );
}

function CarteDuGraphe(props: { carte: CarteProjet }): Noeud {
  const { carte } = props;
  const resume = chaine(carte.resume);
  return (
    <li className="acp-entree">
      <h4 className="acp-entree__nom">
        <Donnee valeur={chaine(carte.titre)} />
      </h4>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.statut}>
          <Etiquette libelle={libelleStatut(carte.statut)} brut={carte.statut} />
        </Ligne>
        <Ligne libelle={T.projets.voie}>
          <Libre texte={libelleVoie(carte.voie)} brut={carte.voie} mono />
        </Ligne>
        <Ligne libelle={T.projets.tour}>
          <Donnee valeur={nombre(carte.tour)} />
        </Ligne>
        <Ligne libelle={T.projets.modeleDemande}>
          <Donnee valeur={chaine(carte.modele)} mono />
        </Ligne>
        <Ligne libelle={T.projets.effort}>
          {chaine(carte.effort) ? (
            <Donnee valeur={chaine(carte.effort)} mono />
          ) : (
            <span className="acp-discret">{T.projets.effortParDefaut}</span>
          )}
        </Ligne>
        <Ligne libelle={T.projets.palier}>
          <Donnee valeur={chaine(carte.palier)} mono />
        </Ligne>
        <Ligne libelle={T.projets.modeleServi}>
          <Donnee valeur={chaine(carte.modele_servi)} />
        </Ligne>
        {chaine(carte.mention) ? (
          <Ligne libelle={T.projets.mention}>
            <Donnee valeur={chaine(carte.mention)} />
          </Ligne>
        ) : null}
        {chaine(carte.carte) ? (
          <Ligne libelle={T.projets.carte}>
            <Donnee valeur={chaine(carte.carte)} mono />
          </Ligne>
        ) : null}
      </dl>
      {resume ? (
        <details className="acp-details">
          <summary>{T.projets.resume}</summary>
          <p className="acp-texte-long">
            <Donnee valeur={resume} />
          </p>
        </details>
      ) : null}
    </li>
  );
}

function Cartes(props: { cartes: CarteProjet[] }): Noeud {
  const groupes = new Map<string, CarteProjet[]>();
  for (const carte of props.cartes) {
    const role = chaine(carte.role) ?? "";
    groupes.set(role, [...(groupes.get(role) ?? []), carte]);
  }
  const connus: string[] = [...ORDRE_DES_ROLES];
  const roles = [...connus.filter((r) => groupes.has(r)), ...[...groupes.keys()].filter((r) => !connus.includes(r))];
  return (
    <Carte titre={T.projets.cartes} id="acp-projet-cartes">
      {props.cartes.length === 0 ? <p className="acp-discret">{T.projets.aucuneCarte}</p> : null}
      {roles.map((role) => (
        <div key={role || "?"} className="acp-groupe">
          <h3 className="acp-sous-titre">
            <Libre texte={libelleRole(role)} brut={role} mono />
          </h3>
          <ul className="acp-entrees">
            {(groupes.get(role) ?? []).map((c, rang) => (
              <CarteDuGraphe key={chaine(c.carte) ?? `${role}-${rang}`} carte={c} />
            ))}
          </ul>
        </div>
      ))}
    </Carte>
  );
}

function Tours(props: { projet: Detail }): Noeud {
  const tours = Array.isArray(props.projet.tours) ? props.projet.tours : [];
  if (tours.length === 0) return null;
  return (
    <Carte titre={T.projets.toursTitre} id="acp-projet-tours">
      {tours.map((t, rang) => {
        const decisions = listeDeChaines(t.decisions);
        return (
          <div key={String(t.tour ?? rang)} className="acp-groupe">
            <h3 className="acp-sous-titre">
              <span>{T.projets.tour}</span> <Donnee valeur={nombre(t.tour)} />
            </h3>
            <p className="acp-texte-long">
              <Donnee valeur={chaine(t.resume)} />
            </p>
            {decisions.length > 0 ? (
              <div>
                <p className="acp-discret">{T.projets.decisions}</p>
                <ul className="acp-noms">
                  {decisions.map((d, i) => (
                    <li key={String(i)}>
                      <Donnee valeur={d} />
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        );
      })}
    </Carte>
  );
}

function QuestionsDuProjet(props: { projet: Detail; naviguer: Naviguer }): Noeud {
  const questions = Array.isArray(props.projet.questions_ouvertes) ? props.projet.questions_ouvertes : [];
  if (questions.length === 0) return null;
  return (
    <Carte titre={T.projets.questionsEnAttente} id="acp-projet-questions">
      <ul className="acp-noms">
        {questions.map((q, rang) => (
          <li key={chaine(q.id) ?? String(rang)} className="acp-question-courte">
            <Etiquette libelle={libelleEtatQuestion(q.etat)} brut={q.etat} />
            <p className="acp-texte-long">
              <Donnee valeur={chaine(q.texte)} />
            </p>
          </li>
        ))}
      </ul>
      <div className="acp-actions">
        <LienVue vue={{ genre: "questions" }} naviguer={props.naviguer}>
          {T.projets.voirQuestions}
        </LienVue>
      </div>
    </Carte>
  );
}

function Journal(props: { projet: Detail }): Noeud {
  const journal = Array.isArray(props.projet.journal) ? props.projet.journal : [];
  return (
    <Carte titre={T.projets.journal} id="acp-projet-journal">
      {journal.length === 0 ? (
        <p className="acp-discret">{T.projets.journalVide}</p>
      ) : (
        <details className="acp-details">
          <summary>
            <span>{T.projets.journalOuvrir}</span> <Donnee valeur={nombre(journal.length)} />
          </summary>
          <ul className="acp-journal">
            {journal.map((j, rang) => (
              <li key={String(rang)}>
                <Horodatage valeur={j.quand} /> <Donnee valeur={chaine(j.action)} mono />{" "}
                <Donnee valeur={chaine(j.acteur)} mono />
                {chaine(j.cible) ? (
                  <span>
                    {" "}
                    <Donnee valeur={chaine(j.cible)} mono />
                  </span>
                ) : null}
                {chaine(j.detail) ? (
                  <span className="acp-journal__detail">
                    <Donnee valeur={chaine(j.detail)} mono />
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Carte>
  );
}

export function DetailProjet(props: {
  id: string;
  jeton: number;
  liste: ListeProjets | null;
  naviguer: Naviguer;
  apres: () => void;
}): Noeud {
  const sondage = useSondage<ReponseDetail>(() => lireProjet(props.id), props.jeton);
  const projet = sondage.valeur?.projet ?? null;
  return (
    <div className="acp-sections">
      <div className="acp-actions">
        <LienVue vue={{ genre: "liste" }} naviguer={props.naviguer}>
          {T.projets.retour}
        </LienVue>
      </div>
      {projet === null && sondage.erreur === null ? <EnChargement /> : null}
      {sondage.erreur !== null ? <BlocRefus erreur={sondage.erreur} /> : null}
      {projet !== null ? (
        <div className="acp-sections">
          <EnTete projet={projet} liste={props.liste} apres={props.apres} />
          <QuestionsDuProjet projet={projet} naviguer={props.naviguer} />
          <Cartes cartes={Array.isArray(projet.cartes) ? projet.cartes : []} />
          <Tours projet={projet} />
          <Journal projet={projet} />
        </div>
      ) : null}
    </div>
  );
}
