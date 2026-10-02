// Vue « détail » d'un projet (GET /v1/projets/{id}) : état, résultat du projet (synthèse du dernier tour, en
// entier), tour et plafonds, cartes groupées par rôle (statut, exécutant, modèle demandé, effort, palier,
// « Modèle servi : Non observé » avant P6, résumé replié : un extrait le DIT, et « Lire le résumé en entier »
// appelle GET /v1/projets/{id}/cartes/{carte}), tours et décisions, questions en attente, journal en français
// (détail technique replié) ; « Mettre en pause » et « Reprendre » appellent les routes réelles.
// Étape P7 : « Qui répond » se change à tout moment pour un projet sur dépôt (POST /v1/projets/{id}/reponses : vaut
// pour les questions SUIVANTES ; rien ne change à l'écran avant la réponse de l'API), et « Clore le projet »
// (POST /v1/projets/{id}/clore) après une confirmation qui dit exactement ce que fait la clôture.
import type * as ReactTypes from "react";
import { T } from "../chaines";
import { Carte, Donnee, EnChargement, Ligne } from "../commun";
import { nombre } from "../format";
import { h, useState, type Noeud } from "../react";
import { chaine, listeDeChaines } from "../types";
import { changerReponses, clore, lireCarte, lireProjet, pauseProjet, repriseProjet } from "./api";
import { BlocRefus, Bouton, EtatDuPoste, Etiquette, Horodatage, LienVue, RetourEnvoi, type Naviguer } from "./briques";
import { useEnvoi } from "./envoi";
import {
  libelleActeurJournal,
  libelleActionJournal,
  libelleEtatProjet,
  libelleEtatQuestion,
  libelleOrigine,
  libellePalier,
  libelleProfil,
  libelleReponses,
  libelleRole,
  libelleStatut,
  libelleVoie,
  ORDRE_DES_ROLES,
} from "./libelles";
import { Avancement } from "./ListeProjets";
import { useDonnees } from "../donnees";
import type {
  CarteLue,
  CarteProjet,
  DetailProjet as Detail,
  ListeProjets,
  ReponseDetail,
  ResultatCloture,
  ResultatReglageReponses,
} from "./types";

const ETATS_REGLABLES = ["creation", "actif", "en_pause"];
type Reponses = "hermes_d_abord" | "proprietaire";

function Libre(props: { texte: string | null; brut: unknown; mono?: boolean }): Noeud {
  return props.texte ? <span>{props.texte}</span> : <Donnee valeur={chaine(props.brut)} mono={props.mono} />;
}

/** « Qui répond » modifiable (cahier P7 § 4.2) : projet sur dépôt, pas encore fini. Le choix n'apparaît qu'après la
 *  réponse de l'API ; le message dit combien de questions ouvertes gardent leur traitement. */
function ChangerQuiRepond(props: { projet: Detail; apres: () => void }): Noeud {
  const { projet } = props;
  const id = chaine(projet.id);
  const actuel: Reponses = projet.reponses === "proprietaire" ? "proprietaire" : "hermes_d_abord";
  const [ouvert, fixerOuvert] = useState(false);
  const [choix, fixerChoix] = useState<Reponses>(actuel);
  const envoi = useEnvoi<ResultatReglageReponses>();
  const reglable = Boolean(id) && Boolean(chaine(projet.depot)) && ETATS_REGLABLES.includes(String(projet.etat));
  if (!reglable && envoi.etat.etat !== "ok") return null;
  const enregistrer = async (evenement: ReactTypes.FormEvent) => {
    evenement.preventDefault();
    if (!id) return;
    if ((await envoi.envoyer(() => changerReponses(id, choix))) !== null) {
      fixerOuvert(false);
      props.apres();
    }
  };
  const resultat = envoi.etat.etat === "ok" ? envoi.etat.resultat : null;
  return (
    <div className="acp-groupe">
      {ouvert ? (
        <form className="acp-formulaire" onSubmit={(e: ReactTypes.FormEvent) => void enregistrer(e)}>
          <div className="acp-champ">
            <label htmlFor="acp-projet-qui-repond">{T.projets.quiRepondSuivantes}</label>
            <select
              id="acp-projet-qui-repond"
              value={choix}
              onChange={(e: ReactTypes.ChangeEvent<HTMLSelectElement>) => fixerChoix(e.target.value as Reponses)}
            >
              <option value="hermes_d_abord">{T.projets.reponsesHermes}</option>
              <option value="proprietaire">{T.projets.reponsesProprietaire}</option>
            </select>
          </div>
          <p className="acp-discret">{T.projets.quiRepondAide}</p>
          <div className="acp-actions">
            <Bouton type="submit" principal libelle={T.projets.enregistrer} desactive={envoi.etat.etat === "envoi"} />
            <Bouton libelle={T.projets.annuler} surClic={() => fixerOuvert(false)} />
          </div>
        </form>
      ) : reglable ? (
        <div className="acp-actions">
          <Bouton
            libelle={T.projets.changerQuiRepond}
            surClic={() => {
              envoi.oublier();
              fixerChoix(actuel);
              fixerOuvert(true);
            }}
          />
        </div>
      ) : null}
      {resultat ? (
        <p className="acp-succes" role="status">
          <span>{T.projets.reglageEnregistre}</span>{" "}
          <Donnee valeur={nombre(resultat.questions_ouvertes_inchangees)} />
        </p>
      ) : (
        <RetourEnvoi etat={envoi.etat} />
      )}
    </div>
  );
}

/** « Clore le projet » (cahier P7 § 10) : projet actif ou en pause ; la confirmation dit exactement ce que fait la
 *  clôture ; le résultat vient de la réponse de l'API (état atteint, cartes archivées, questions annulées, branches
 *  restées sur l'exécutant). */
function Cloture(props: { projet: Detail; apres: () => void }): Noeud {
  const { projet } = props;
  const id = chaine(projet.id);
  const [confirmation, fixerConfirmation] = useState(false);
  const envoi = useEnvoi<ResultatCloture>();
  const ouvert = projet.etat === "actif" || projet.etat === "en_pause";
  const resultat = envoi.etat.etat === "ok" ? envoi.etat.resultat : null;
  if (!id || (!ouvert && resultat === null)) return null;
  const confirmer = async () => {
    if ((await envoi.envoyer(() => clore(id))) !== null) {
      fixerConfirmation(false);
      props.apres();
    }
  };
  const branches = listeDeChaines(resultat?.branches_rapportees);
  return (
    <div className="acp-groupe">
      {resultat ? (
        <div className="acp-succes" role="status">
          <p>{resultat.etat === "termine" ? T.projets.closTermine : T.projets.closAbandonne}</p>
          <p>
            <span>{T.projets.cartesArchivees}</span> <Donnee valeur={listeDeChaines(resultat.cartes_archivees).length} />
            <span> {T.commun.separateur} </span>
            <span>{T.projets.questionsAnnulees}</span> <Donnee valeur={nombre(resultat.questions_annulees)} />
          </p>
          {branches.length > 0 ? (
            <div>
              <p>{T.projets.branchesRestent}</p>
              <ul className="acp-noms">
                {branches.map((b) => (
                  <li key={b}>
                    <Donnee valeur={b} mono />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : confirmation ? (
        <div className="acp-confirmation" role="group" aria-labelledby="acp-clore-question">
          <p id="acp-clore-question">{T.projets.cloreQuestion}</p>
          <ul className="acp-noms">
            <li>{T.projets.clorePoint1}</li>
            <li>{T.projets.clorePoint2}</li>
            <li>{T.projets.clorePoint3}</li>
            <li>{T.projets.clorePoint4}</li>
          </ul>
          <div className="acp-actions">
            <Bouton
              libelle={T.projets.cloreConfirmer}
              danger
              surClic={() => void confirmer()}
              desactive={envoi.etat.etat === "envoi"}
            />
            <Bouton
              libelle={T.projets.annuler}
              surClic={() => {
                fixerConfirmation(false);
                envoi.oublier();
              }}
            />
          </div>
        </div>
      ) : (
        <div className="acp-actions">
          <Bouton libelle={T.projets.clore} danger surClic={() => fixerConfirmation(true)} />
        </div>
      )}
      {resultat ? null : <RetourEnvoi etat={envoi.etat} />}
    </div>
  );
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
          {chaine(projet.depot) ? (
            <Libre texte={libelleReponses(projet.reponses)} brut={projet.reponses} mono />
          ) : (
            <span>{T.projets.reponsesSansObjetCourt}</span>
          )}
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
      <ChangerQuiRepond projet={projet} apres={props.apres} />
      <Cloture projet={projet} apres={props.apres} />
    </section>
  );
}

/** Résumé d'une carte : un extrait (500 caractères) le dit, avec la longueur entière, et se lit en entier
 *  par la route de lecture d'une carte (texte masqué, borné à 100 000 caractères, ce qui se dit aussi). */
function Resume(props: { projet: string | null; carte: CarteProjet }): Noeud {
  const resume = chaine(props.carte.resume);
  const identifiant = chaine(props.carte.carte);
  const [entier, fixerEntier] = useState<CarteLue | null>(null);
  const lecture = useEnvoi<{ carte?: CarteLue }>();
  if (!resume) return null;
  const tronque = props.carte.resume_tronque === true && entier === null;
  const lire = async () => {
    if (!props.projet || !identifiant) return;
    const lu = await lecture.envoyer(() => lireCarte(props.projet as string, identifiant));
    if (lu?.carte) fixerEntier(lu.carte);
  };
  return (
    <details className="acp-details">
      <summary>{T.projets.resume}</summary>
      <p className="acp-texte-long">
        <Donnee valeur={chaine(entier?.resume) ?? resume} />
      </p>
      {tronque ? (
        <div>
          <p className="acp-discret">
            <span>{T.projets.extrait}</span> <Donnee valeur={nombre(resume.length)} />{" "}
            <span>{T.projets.caracteresSur}</span> <Donnee valeur={nombre(props.carte.resume_longueur)} />
          </p>
          {props.projet && identifiant ? (
            <div className="acp-actions">
              <Bouton libelle={T.projets.lireEnEntier} surClic={() => void lire()} desactive={lecture.etat.etat === "envoi"} />
            </div>
          ) : null}
          <RetourEnvoi etat={lecture.etat} />
        </div>
      ) : null}
      {entier?.tronque === true ? <p className="acp-discret">{T.projets.texteBorne}</p> : null}
    </details>
  );
}

function CarteDuGraphe(props: { projet: string | null; carte: CarteProjet }): Noeud {
  const { carte } = props;
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
          <Libre texte={libellePalier(carte.palier)} brut={carte.palier} mono />
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
      <Resume projet={props.projet} carte={carte} />
    </li>
  );
}

function Cartes(props: { projet: string | null; cartes: CarteProjet[] }): Noeud {
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
              <CarteDuGraphe key={chaine(c.carte) ?? `${role}-${rang}`} projet={props.projet} carte={c} />
            ))}
          </ul>
        </div>
      ))}
    </Carte>
  );
}

/** Résultat du projet : la synthèse FAITE du dernier tour, en entier (le livrable d'un projet sans dépôt). */
function Resultat(props: { projet: Detail }): Noeud {
  const resultat = props.projet.resultat;
  const texte = chaine(resultat?.texte);
  if (!texte) return null;
  return (
    <Carte titre={T.projets.resultatTitre} id="acp-projet-resultat">
      <p className="acp-discret">
        <span>{T.projets.resultatIntro}</span> <span>{T.projets.tour}</span> <Donnee valeur={nombre(resultat?.tour)} />
      </p>
      <p className="acp-texte-long">
        <Donnee valeur={texte} />
      </p>
      {resultat?.tronque === true ? <p className="acp-discret">{T.projets.texteBorne}</p> : null}
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
            {journal.map((j, rang) => {
              const acteur = libelleActeurJournal(j.acteur);
              return (
                <li key={String(rang)}>
                  <Horodatage valeur={j.quand} /> <Libre texte={libelleActionJournal(j.action)} brut={j.action} mono />{" "}
                  <span className="acp-discret">
                    {acteur.libelle ? <span>{acteur.libelle}</span> : null}
                    {acteur.libelle && acteur.donnee ? " " : null}
                    {acteur.donnee ? <Donnee valeur={acteur.donnee} mono /> : null}
                  </span>
                  {chaine(j.detail) || chaine(j.cible) ? (
                    <details className="acp-journal__detail">
                      <summary>{T.projets.detailTechnique}</summary>
                      {chaine(j.cible) ? <Donnee valeur={chaine(j.cible)} mono /> : null}{" "}
                      {chaine(j.detail) ? <Donnee valeur={chaine(j.detail)} mono /> : null}
                    </details>
                  ) : null}
                </li>
              );
            })}
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
  const sondage = useDonnees<ReponseDetail>(() => lireProjet(props.id), props.jeton, ["projets", "questions", "pause"]);
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
          <Resultat projet={projet} />
          <Cartes projet={chaine(projet.id)} cartes={Array.isArray(projet.cartes) ? projet.cartes : []} />
          <Tours projet={projet} />
          <Journal projet={projet} />
        </div>
      ) : null}
    </div>
  );
}
