// Page d'accueil d'ACP : remplace la page « / » du tableau de bord (tab.override), qui
// redirigeait vers /sessions. Pensée d'abord pour le téléphone (une colonne, cibles de 44 px).
// Aucune donnée inventée : une valeur illisible s'affiche « Inconnu », le poste « Non configuré ».
// Aucun repère <header>/<footer> : le tableau de bord porte déjà les siens (axe :
// landmark-no-duplicate-banner, relevé au format téléphone).
import { T } from "../chaines";
import { lireMeta, lireSessions } from "../api";
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
import { court, dateRelative, nombre, versMillisecondes } from "../format";
import { h, type Noeud } from "../react";
import { chaine, type Meta, type PageSessions } from "../types";

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

function CartePoste(): Noeud {
  return (
    <Carte titre={T.accueil.poste} id="acp-accueil-poste">
      <p>
        <Pastille etat="nonConfigure" />
      </p>
      <p className="acp-discret">{T.accueil.posteNote}</p>
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
          <Lien vers="/chat">{T.accueil.discussion}</Lien>
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
  return (
    <div className="acp-page" data-acp-racine="accueil">
      <div className="acp-entete">
        <h1 className="acp-titre">{T.accueil.titre}</h1>
        <p className="acp-discret">{T.accueil.intro}</p>
      </div>
      {meta.etat === "chargement" ? <EnChargement /> : null}
      {meta.etat === "erreur" ? <BlocErreur erreur={meta.erreur} message={T.accueil.metaIndisponible} /> : null}
      <div className="acp-grille">
        {meta.etat === "ok" ? <CarteHermes meta={meta.valeur} /> : null}
        {meta.etat === "ok" ? <CarteGarde meta={meta.valeur} /> : null}
        {meta.etat === "ok" ? <CartePersona meta={meta.valeur} /> : null}
        {meta.etat === "ok" ? <CarteCatalogue meta={meta.valeur} /> : null}
        <CarteSessions />
        <CartePoste />
        <CarteRaccourcis />
      </div>
      <Pied meta={meta.etat === "ok" ? meta.valeur : null} />
    </div>
  );
}
