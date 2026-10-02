// Page d'accueil d'ACP : remplace la page « / » du tableau de bord (tab.override), qui redirigeait vers /sessions.
// Étape P7 (cahier P7 § 8, décision P7-7) : UNE lecture agrégée (GET /v1/accueil), la même au téléphone, dans le
// navigateur du PC et, s'il le veut, pour le desktop ; MÊME ORDRE et MÊMES TEXTES à toutes les largeurs (une colonne
// à 390 px, trois au bureau) :
//   1. À traiter par vous (compte, trois premières demandes, discussions en attente comptées par le client) ;
//   2. Projets en cours (avancement « n sur m », dernière note) ;
//   3. Exécutant (état réel, carte en cours, voies fermées et leur raison) ;
//   4. Quotas (par voie, source et date du relevé) ;
//   5. Notifications (canal, notification de test) et bilan quotidien (tâche cron du propriétaire) ;
//   6. Discussions (cinq dernières sessions) ;
//   7. Système (Hermes, garde, persona, catalogue), puis les raccourcis.
// Temps réel par le flux d'invalidation (tous les sujets), sondage de 15 s en repli. Aucune donnée inventée : un bloc
// illisible le dit avec sa raison ; la carte « Poste » figée sur « Non configuré » de P3 a disparu (elle était fausse
// depuis que l'exécutant existe). Aucun repère <header>/<footer> : le tableau de bord porte déjà les siens (axe :
// landmark-no-duplicate-banner, relevé au format téléphone).
import { T } from "../chaines";
import { lireMeta, lireSessions } from "../api";
import { EtatActualisation } from "../actualisation";
import {
  BlocErreur,
  Carte,
  Donnee,
  EnChargement,
  Ligne,
  Lien,
  Pastille,
  useChargement,
  type CleEtat,
} from "../commun";
import { useDonnees } from "../donnees";
import { SUJETS } from "../flux";
import { court, dateRelative, nombre, versMillisecondes } from "../format";
import { lireDiscussionsEnAttente } from "../jsonrpc/discussions";
import { h, useState, type Noeud } from "../react";
import { chaine, type Meta, type PageSessions } from "../types";
import { BandeauPause } from "../projets/BandeauPause";
import { Etiquette } from "../projets/briques";
import { libelleEtatProjet } from "../projets/libelles";
import { Avancement } from "../projets/ListeProjets";
import { Notifications } from "../projets/Notifications";
import { lireAccueil, type Accueil as DonneesAccueil, type ProjetAccueil } from "./accueil-api";
import { CarteATraiter } from "./CarteATraiter";
import { CarteBilan } from "./CarteBilan";
import { CarteExecutant, CarteQuotas } from "./CarteExecutant";

export function etatPersona(meta: Meta | null): CleEtat {
  switch (meta?.demarrage?.soul?.etat) {
    case "a_jour":
      return "aJour";
    case "depose":
      return "deposee";
    case "divergent":
      return "divergente";
    case "non_ordinaire":
      return "nonOrdinaire";
    default:
      return "inconnu";
  }
}

export function etatConformite(conforme: unknown): CleEtat {
  return conforme === true ? "conforme" : conforme === false ? "nonConforme" : "inconnu";
}

export function etatContext7(valeur: unknown): CleEtat {
  return valeur === "connecte" ? "connecte" : valeur === "hors_ligne" ? "horsLigne" : "inconnu";
}

function CarteHermes(props: { meta: Meta }): Noeud {
  const { hermes, image, deploiement } = props.meta;
  return (
    <Carte titre={T.accueil.hermes} id="acp-accueil-hermes">
      <dl className="acp-liste">
        <Ligne libelle={T.accueil.version}>
          <Donnee valeur={chaine(hermes?.version)} mono />
        </Ligne>
        <Ligne libelle={T.accueil.versionTestee}>
          <Donnee valeur={chaine(hermes?.version_testee)} mono />
        </Ligne>
        <Ligne libelle={T.accueil.conformite}>
          <Pastille etat={etatConformite(hermes?.conforme)} />
        </Ligne>
        <Ligne libelle={T.accueil.image}>
          <Donnee valeur={court(image?.condensat_index)} mono />
        </Ligne>
        <Ligne libelle={T.accueil.commit}>
          <Donnee valeur={court(deploiement?.commit)} mono />
        </Ligne>
      </dl>
    </Carte>
  );
}

function CarteGarde(props: { meta: Meta }): Noeud {
  const garde = props.meta.garde_execution;
  const presente = garde?.presente_dans_le_gestionnaire;
  const admis = Array.isArray(garde?.outils_admis) ? garde.outils_admis.length : null;
  return (
    <Carte titre={T.accueil.garde} id="acp-accueil-garde">
      <dl className="acp-liste">
        <Ligne libelle={T.accueil.gardeEtat}>
          {presente === true ? (
            <Pastille etat="active" />
          ) : presente === false ? (
            <Pastille etat="absente" />
          ) : (
            <Pastille etat="inconnu" />
          )}
        </Ligne>
        <Ligne libelle={T.accueil.outilsAdmis}>
          <Donnee valeur={nombre(admis)} />
        </Ligne>
      </dl>
      {chaine(garde?.alerte) ? (
        <p className="acp-alerte-texte">
          <Donnee valeur={chaine(garde?.alerte)} />
        </p>
      ) : null}
    </Carte>
  );
}

function CartePersona(props: { meta: Meta }): Noeud {
  return (
    <Carte titre={T.accueil.persona} id="acp-accueil-persona">
      <dl className="acp-liste">
        <Ligne libelle={T.accueil.personaEtat}>
          <Pastille etat={etatPersona(props.meta)} />
        </Ligne>
      </dl>
    </Carte>
  );
}

function CarteCatalogue(props: { meta: Meta }): Noeud {
  const resume = props.meta.catalogue ?? null;
  return (
    <Carte titre={T.accueil.catalogue} id="acp-accueil-catalogue">
      <dl className="acp-liste">
        <Ligne libelle={T.accueil.skillsAcp}>
          <Donnee valeur={nombre(resume?.skills_actives)} />
          <span className="acp-discret"> {T.commun.separateur} </span>
          <Donnee valeur={nombre(resume?.skills_attendues)} />
          <span className="acp-discret"> {T.accueil.skillsAttendues}</span>
        </Ligne>
        <Ligne libelle={T.accueil.context7}>
          <Pastille etat={etatContext7(resume?.context7)} />
        </Ligne>
      </dl>
      <p>
        <Lien vers="/catalogue">{T.accueil.ouvrirCatalogue}</Lien>
      </p>
    </Carte>
  );
}

/** Date relative en français ; l'horodatage exact reste lisible par les technologies
 *  d'assistance (attribut dateTime). Absent ou illisible : « Inconnu », jamais 1970. */
function Horodatage(props: { valeur: unknown }): Noeud {
  const ms = versMillisecondes(props.valeur);
  if (ms === null) return <Donnee valeur={null} />;
  return (
    <time dateTime={new Date(ms).toISOString()}>
      <Donnee valeur={dateRelative(ms)} />
    </time>
  );
}

function CarteSessions(): Noeud {
  const chargement = useChargement<PageSessions>(lireSessions);
  let contenu: Noeud;
  if (chargement.etat === "chargement") {
    contenu = <EnChargement />;
  } else if (chargement.etat === "erreur") {
    contenu = <BlocErreur erreur={chargement.erreur} />;
  } else {
    const sessions = Array.isArray(chargement.valeur.sessions) ? chargement.valeur.sessions.slice(0, 5) : [];
    contenu =
      sessions.length === 0 ? (
        <p className="acp-discret">{T.accueil.aucuneSession}</p>
      ) : (
        <ul className="acp-sessions">
          {sessions.map((session, rang) => (
            <li key={session.id ?? String(rang)} className="acp-session">
              <span className="acp-session__titre">
                {chaine(session.title) ? <Donnee valeur={chaine(session.title)} /> : <span>{T.accueil.sansTitre}</span>}
              </span>
              <span className="acp-session__meta">
                <Horodatage valeur={session.last_active} />
                <span className="acp-discret"> {T.commun.separateur} </span>
                <Donnee valeur={nombre(session.message_count)} />
                <span className="acp-discret"> {T.accueil.messages}</span>
              </span>
            </li>
          ))}
        </ul>
      );
  }
  return (
    <Carte titre={T.accueil.sessions} id="acp-accueil-sessions">
      {contenu}
      <p>
        <Lien vers="/sessions">{T.accueil.toutesSessions}</Lien>
      </p>
    </Carte>
  );
}

function CarteProjets(props: { bloc: DonneesAccueil["projets"]; illisible: string | null }): Noeud {
  const bloc = props.bloc ?? null;
  const liste = Array.isArray(bloc?.liste) ? bloc.liste : [];
  return (
    <Carte titre={T.accueil.projetsTitre} id="acp-accueil-projets">
      {bloc === null ? (
        <p className="acp-alerte-texte">
          <span>{T.accueil.blocIllisible}</span> <Donnee valeur={props.illisible} />
        </p>
      ) : (
        <div className="acp-sections">
          <dl className="acp-liste">
            <Ligne libelle={T.accueil.projetsEnCours}>
              <Donnee valeur={nombre(bloc.en_cours)} />
            </Ligne>
            <Ligne libelle={T.accueil.projetsEnPause}>
              <Donnee valeur={nombre(bloc.en_pause)} />
            </Ligne>
            <Ligne libelle={T.accueil.projetsTermines7j}>
              <Donnee valeur={nombre(bloc.termines_7j)} />
            </Ligne>
          </dl>
          {liste.length === 0 ? (
            <p className="acp-discret">{T.accueil.aucunProjetOuvert}</p>
          ) : (
            <ul className="acp-noms">
              {liste.map((p: ProjetAccueil, rang) => {
                const id = chaine(p.id);
                return (
                  <li key={id ?? String(rang)} className="acp-projet-court">
                    <p className="acp-etat">
                      {id ? (
                        <Lien vers={`/projets?projet=${encodeURIComponent(id)}`}>
                          <Donnee valeur={chaine(p.titre)} />
                        </Lien>
                      ) : (
                        <Donnee valeur={chaine(p.titre)} />
                      )}{" "}
                      <Etiquette libelle={libelleEtatProjet(p.etat, p.etat_derive)} brut={p.etat} />
                    </p>
                    <Avancement faites={p.faites} total={p.total} />
                    {chaine(p.derniere_note) ? (
                      <p className="acp-discret">
                        <Donnee valeur={chaine(p.derniere_note)} />
                      </p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
      <p>
        <Lien vers="/projets">{T.accueil.ouvrirProjets}</Lien>
      </p>
    </Carte>
  );
}

function CarteRaccourcis(): Noeud {
  return (
    <Carte titre={T.accueil.raccourcis} id="acp-accueil-raccourcis">
      <ul className="acp-raccourcis">
        <li>
          <Lien vers="/projets">{T.accueil.lienProjets}</Lien>
        </li>
        <li>
          <Lien vers="/discussion">{T.accueil.discussion}</Lien>
        </li>
        <li>
          <Lien vers="/sessions">{T.accueil.lienSessions}</Lien>
        </li>
        <li>
          <Lien vers="/kanban">{T.accueil.kanban}</Lien>
        </li>
        <li>
          <Lien vers="/catalogue">{T.accueil.lienCatalogue}</Lien>
        </li>
      </ul>
    </Carte>
  );
}

function Pied(props: { meta: Meta | null }): Noeud {
  return (
    <div className="acp-pied">
      <span>{T.accueil.piedAcp}</span> <Donnee valeur={chaine(props.meta?.greffon?.version)} mono />{" "}
      <span>{T.commun.separateur}</span> <span>{T.accueil.piedPropulse}</span>{" "}
      <Donnee valeur={chaine(props.meta?.hermes?.version)} mono /> <span>{T.accueil.piedLicence}</span>
    </div>
  );
}

export function Accueil(): Noeud {
  const meta = useChargement<Meta>(() => lireMeta());
  // Incrémenté après chaque geste (pause levée, bilan créé) : les lectures se refont aussitôt.
  const [jeton, fixerJeton] = useState(0);
  const apres = () => fixerJeton((j) => j + 1);
  const lecture = useDonnees(lireAccueil, jeton, SUJETS);
  const discussions = useDonnees(lireDiscussionsEnAttente, jeton, ["discussions"]);
  const accueil = lecture.valeur;
  const illisibles = accueil?.illisibles ?? {};
  const raison = (bloc: string): string | null => (typeof illisibles[bloc] === "string" ? illisibles[bloc] : null);
  const pause = accueil?.pause_generale && typeof accueil.pause_generale === "object" ? accueil.pause_generale : null;
  return (
    <div className="acp-page" data-acp-racine="accueil">
      <div className="acp-entete">
        <h1 className="acp-titre">{T.accueil.titre}</h1>
        <p className="acp-discret">{T.accueil.intro}</p>
      </div>
      {pause ? <BandeauPause pause={pause} apres={apres} /> : null}
      {accueil === null && lecture.erreur === null ? <EnChargement /> : null}
      {accueil === null && lecture.erreur !== null ? (
        <BlocErreur erreur={lecture.erreur} message={T.accueil.accueilIndisponible} />
      ) : null}
      {accueil !== null && lecture.erreur !== null ? (
        <p className="acp-alerte-texte" role="status">
          {T.accueil.actualisationImpossible}
        </p>
      ) : null}
      <div className="acp-grille acp-grille--accueil">
        {accueil !== null ? (
          <CarteATraiter aTraiter={accueil.a_traiter} chezHermes={accueil.chez_hermes} discussions={discussions.valeur}
                         illisible={raison("a_traiter")} />
        ) : null}
        {accueil !== null ? <CarteProjets bloc={accueil.projets} illisible={raison("projets")} /> : null}
        {accueil !== null ? <CarteExecutant executant={accueil.executant} illisible={raison("executant")} /> : null}
        {accueil !== null ? <CarteQuotas quotas={accueil.quotas} illisible={raison("quotas")} /> : null}
        {accueil !== null ? <Notifications etat={accueil.notifications} /> : null}
        {accueil !== null ? <CarteBilan notifications={accueil.notifications} jeton={jeton} apres={apres} /> : null}
        <CarteSessions />
        {meta.etat === "ok" ? <CarteHermes meta={meta.valeur} /> : null}
        {meta.etat === "ok" ? <CarteGarde meta={meta.valeur} /> : null}
        {meta.etat === "ok" ? <CartePersona meta={meta.valeur} /> : null}
        {meta.etat === "ok" ? <CarteCatalogue meta={meta.valeur} /> : null}
        <CarteRaccourcis />
      </div>
      {meta.etat === "chargement" ? <EnChargement /> : null}
      {meta.etat === "erreur" ? <BlocErreur erreur={meta.erreur} message={T.accueil.metaIndisponible} /> : null}
      <EtatActualisation />
      <Pied meta={meta.etat === "ok" ? meta.valeur : null} />
    </div>
  );
}
