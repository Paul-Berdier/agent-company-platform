// Onglet « Catalogue » : skills et serveurs MCP retenus par ACP, EN LECTURE SEULE.
// Aucun bouton d'installation ni d'action : le catalogue change par une PR (verrou
// hermes/catalogue/catalogue.lock.json), jamais depuis le tableau de bord.
//
// Deux sources, jamais confondues :
// - GET /api/plugins/acp-poste/v1/catalogue : le verrou et l'état tel que le chargeur de skills
//   de Hermes le voit ; indisponible ⇒ « Catalogue ACP indisponible », rien d'inventé ;
// - GET /api/skills : ce que le tableau de bord de Hermes calcule lui-même.
import { T } from "../chaines";
import { lireCatalogue, lireSkills } from "../api";
import { BlocErreur, Carte, Donnee, EnChargement, Ligne, Pastille, useChargement, type CleEtat } from "../commun";
import { court, nombre } from "../format";
import { h, useMemo, useState, type Noeud } from "../react";
import {
  chaine,
  listeDeChaines,
  type Catalogue as DonneesCatalogue,
  type McpCatalogue,
  type SkillCatalogue,
  type SkillHermes,
  type SourceCatalogue,
} from "../types";

const TOUS = "";

export const LIBELLES_PROFILS: Record<string, string> = {
  base: T.catalogue.profilBase,
  web: T.catalogue.profilWeb,
  recherche: T.catalogue.profilRecherche,
  donnees: T.catalogue.profilDonnees,
};

export function etatEntree(etat: unknown): CleEtat {
  switch (etat) {
    case "active":
    case "actif":
      return "active";
    case "desactivee":
    case "desactive":
      return "desactivee";
    case "absente":
    case "absent":
      return "absente";
    // Côté poste (relecture de P3) : rien n'est promis hors du plan d'autonomie. Une skill du
    // poste est une candidate non planifiée ; un serveur MCP n'est « reporte-p8 » que si le plan le
    // prévoit en P8, sinon « hors-v1 ».
    case "candidate-poste":
      return "candidate";
    case "reporte-p8":
    case "reportee-p8":
      return "prevueP8";
    case "hors-v1":
      return "horsV1";
    case "ambigue":
      return "ambigue";
    case "livree":
      return "livree";
    case "connecte":
      return "connecte";
    case "hors_ligne":
      return "horsLigne";
    default:
      return "inconnu";
  }
}

function Cible(props: { cible: unknown }): Noeud {
  if (props.cible === "hermes") return <span>{T.catalogue.cibleHermes}</span>;
  if (props.cible === "poste") return <span>{T.catalogue.ciblePoste}</span>;
  return <Donnee valeur={chaine(props.cible)} />;
}

function Profil(props: { id: string }): Noeud {
  const libelle = LIBELLES_PROFILS[props.id];
  return libelle ? <span>{libelle}</span> : <Donnee valeur={props.id} />;
}

function Etat(props: { etat: unknown }): Noeud {
  const cle = etatEntree(props.etat);
  return (
    <span className="acp-etat">
      <Pastille etat={cle} />
      {cle === "inconnu" && chaine(props.etat) ? <Donnee valeur={chaine(props.etat)} mono /> : null}
    </span>
  );
}

function libelleSource(nom: string | null, sources: Record<string, SourceCatalogue>): string | null {
  if (!nom) return null;
  const commit = court(sources[nom]?.commit, 8);
  return commit ? `${nom}@${commit}` : nom;
}

/** Liste d'écarts : chaînes ou objets portant un nom ; toute autre forme est ignorée. */
function nomsDeListe(valeur: unknown): string[] {
  if (!Array.isArray(valeur)) return [];
  return valeur
    .map((v) => (typeof v === "string" ? v : v && typeof v === "object" ? chaine((v as { nom?: unknown }).nom) : null))
    .filter((v): v is string => !!v);
}

function EntreeSkill(props: { skill: SkillCatalogue; sources: Record<string, SourceCatalogue> }): Noeud {
  const { skill, sources } = props;
  const source = chaine(skill.source);
  const profils = listeDeChaines(skill.profils);
  return (
    <li className="acp-entree">
      <h3 className="acp-entree__nom">
        <Donnee valeur={chaine(skill.nom)} mono />
      </h3>
      {chaine(skill.description_fr) ? (
        <p>
          <Donnee valeur={chaine(skill.description_fr)} />
        </p>
      ) : null}
      <dl className="acp-liste">
        <Ligne libelle={T.catalogue.source}>
          <Donnee valeur={libelleSource(source, sources)} mono />
        </Ligne>
        <Ligne libelle={T.catalogue.licence}>
          <Donnee valeur={source ? chaine(sources[source]?.licence) : null} />
        </Ligne>
        <Ligne libelle={T.catalogue.cible}>
          <Cible cible={skill.cible} />
        </Ligne>
        <Ligne libelle={T.catalogue.profil}>
          {profils.length === 0 ? (
            <Donnee valeur={null} />
          ) : (
            profils.map((p, rang) => (
              <span key={p} className="acp-profil">
                {rang > 0 ? <span className="acp-discret"> {T.commun.separateur} </span> : null}
                <Profil id={p} />
              </span>
            ))
          )}
        </Ligne>
        <Ligne libelle={T.catalogue.etat}>
          <Etat etat={skill.etat} />
        </Ligne>
      </dl>
      {chaine(skill.raison) ? (
        <p className="acp-discret">
          <Donnee valeur={chaine(skill.raison)} />
        </p>
      ) : null}
    </li>
  );
}

function EntreeMcp(props: { mcp: McpCatalogue }): Noeud {
  const { mcp } = props;
  const outils = listeDeChaines(mcp.outils_hermes);
  return (
    <li className="acp-entree">
      <h3 className="acp-entree__nom">
        <Donnee valeur={chaine(mcp.nom)} mono />
      </h3>
      <dl className="acp-liste">
        <Ligne libelle={T.catalogue.cible}>
          <Cible cible={mcp.cible} />
        </Ligne>
        <Ligne libelle={T.catalogue.etat}>
          <Etat etat={mcp.connexion ?? mcp.etat} />
        </Ligne>
        <Ligne libelle={T.catalogue.outils}>
          {outils.length === 0 ? (
            <Donnee valeur={null} />
          ) : (
            <ul className="acp-outils">
              {outils.map((o) => (
                <li key={o}>
                  <Donnee valeur={o} mono />
                </li>
              ))}
            </ul>
          )}
        </Ligne>
      </dl>
      {chaine(mcp.raison) ? (
        <p className="acp-discret">
          <Donnee valeur={chaine(mcp.raison)} />
        </p>
      ) : null}
    </li>
  );
}

function ListeEcarts(props: { titre: string; noms: string[] }): Noeud {
  if (props.noms.length === 0) return null;
  return (
    <div className="acp-ecart">
      <h3 className="acp-sous-titre">{props.titre}</h3>
      <ul className="acp-noms">
        {props.noms.map((n) => (
          <li key={n}>
            <Donnee valeur={n} mono />
          </li>
        ))}
      </ul>
    </div>
  );
}

function Choix(props: {
  id: string;
  libelle: string;
  valeur: string;
  changer: (v: string) => void;
  toutLibelle: string;
  options: Array<{ valeur: string; libelle: Noeud; donnee: boolean }>;
}): Noeud {
  return (
    <div className="acp-choix">
      <label htmlFor={props.id}>{props.libelle}</label>
      <select id={props.id} value={props.valeur} onChange={(e) => props.changer((e.target as HTMLSelectElement).value)}>
        <option value={TOUS}>{props.toutLibelle}</option>
        {props.options.map((o) =>
          o.donnee ? (
            <option key={o.valeur} value={o.valeur} data-acp-donnee="">
              {o.libelle}
            </option>
          ) : (
            <option key={o.valeur} value={o.valeur}>
              {o.libelle}
            </option>
          ),
        )}
      </select>
    </div>
  );
}

function VueCatalogue(props: { donnees: DonneesCatalogue }): Noeud {
  const { donnees } = props;
  const [profil, fixerProfil] = useState<string>(TOUS);
  const [source, fixerSource] = useState<string>(TOUS);
  const [cible, fixerCible] = useState<string>(TOUS);
  const sources: Record<string, SourceCatalogue> =
    donnees.sources && typeof donnees.sources === "object" ? donnees.sources : {};
  const skills = Array.isArray(donnees.skills) ? donnees.skills : [];
  const mcp = Array.isArray(donnees.mcp) ? donnees.mcp : [];

  const idsProfils = useMemo(() => {
    const ids = new Set<string>(
      donnees.profils && typeof donnees.profils === "object" ? Object.keys(donnees.profils) : [],
    );
    for (const s of skills) for (const p of listeDeChaines(s.profils)) ids.add(p);
    return [...ids].sort();
  }, [donnees]);
  const idsSources = useMemo(() => {
    const ids = new Set<string>(Object.keys(sources));
    for (const s of skills) if (chaine(s.source)) ids.add(s.source as string);
    return [...ids].sort();
  }, [donnees]);

  const retenues = skills.filter(
    (s) =>
      (profil === TOUS || listeDeChaines(s.profils).includes(profil)) &&
      (source === TOUS || s.source === source) &&
      (cible === TOUS || s.cible === cible),
  );
  const mcpRetenus = mcp.filter((m) => cible === TOUS || m.cible === cible);
  const horsCatalogue = nomsDeListe(donnees.hors_catalogue);
  const collisions = nomsDeListe(donnees.collisions);
  const nonAppliquees = nomsDeListe(donnees.desactivations_non_appliquees);
  const alertes = listeDeChaines(donnees.alertes);

  return (
    <div className="acp-sections">
      {alertes.length > 0 ? (
        <Carte titre={T.catalogue.alertes} id="acp-catalogue-alertes">
          <ul className="acp-noms">
            {alertes.map((a, rang) => (
              <li key={String(rang)}>
                <Donnee valeur={a} />
              </li>
            ))}
          </ul>
        </Carte>
      ) : null}
      <fieldset className="acp-filtres">
        <legend>{T.catalogue.filtres}</legend>
        <Choix
          id="acp-filtre-profil"
          libelle={T.catalogue.profil}
          valeur={profil}
          changer={fixerProfil}
          toutLibelle={T.catalogue.tous}
          options={idsProfils.map((p) => ({
            valeur: p,
            libelle: LIBELLES_PROFILS[p] ?? p,
            donnee: !LIBELLES_PROFILS[p],
          }))}
        />
        <Choix
          id="acp-filtre-source"
          libelle={T.catalogue.source}
          valeur={source}
          changer={fixerSource}
          toutLibelle={T.catalogue.toutes}
          options={idsSources.map((s) => ({ valeur: s, libelle: s, donnee: true }))}
        />
        <Choix
          id="acp-filtre-cible"
          libelle={T.catalogue.cible}
          valeur={cible}
          changer={fixerCible}
          toutLibelle={T.catalogue.toutes}
          options={[
            { valeur: "hermes", libelle: T.catalogue.cibleHermes, donnee: false },
            { valeur: "poste", libelle: T.catalogue.ciblePoste, donnee: false },
          ]}
        />
      </fieldset>
      <Carte titre={T.catalogue.skills} id="acp-catalogue-skills">
        {retenues.length === 0 ? (
          <p className="acp-discret">{T.catalogue.aucuneEntree}</p>
        ) : (
          <ul className="acp-entrees">
            {retenues.map((s, rang) => (
              <EntreeSkill key={chaine(s.nom) ?? String(rang)} skill={s} sources={sources} />
            ))}
          </ul>
        )}
      </Carte>
      <Carte titre={T.catalogue.mcp} id="acp-catalogue-mcp">
        {mcpRetenus.length === 0 ? (
          <p className="acp-discret">{T.catalogue.aucuneEntree}</p>
        ) : (
          <ul className="acp-entrees">
            {mcpRetenus.map((m, rang) => (
              <EntreeMcp key={chaine(m.nom) ?? String(rang)} mcp={m} />
            ))}
          </ul>
        )}
      </Carte>
      <Carte titre={T.catalogue.ecarts} id="acp-catalogue-ecarts">
        {horsCatalogue.length + collisions.length + nonAppliquees.length === 0 ? (
          <p className="acp-discret">{T.catalogue.aucunEcart}</p>
        ) : null}
        <ListeEcarts titre={T.catalogue.horsCatalogue} noms={horsCatalogue} />
        <ListeEcarts titre={T.catalogue.collisions} noms={collisions} />
        <ListeEcarts titre={T.catalogue.desactivationsNonAppliquees} noms={nonAppliquees} />
      </Carte>
    </div>
  );
}

function VueHermes(): Noeud {
  const skills = useChargement<SkillHermes[]>(lireSkills);
  let contenu: Noeud;
  if (skills.etat === "chargement") contenu = <EnChargement />;
  else if (skills.etat === "erreur") contenu = <BlocErreur erreur={skills.erreur} />;
  else {
    const liste = Array.isArray(skills.valeur) ? skills.valeur : [];
    const activees = liste.filter((s) => s.enabled === true);
    const desactivees = liste.filter((s) => s.enabled === false);
    const tries = [...liste].sort((a, b) => String(a.name).localeCompare(String(b.name)));
    const etat = (s: SkillHermes): CleEtat => (s.enabled === true ? "activee" : s.enabled === false ? "desactivee" : "inconnu");
    contenu = (
      <div>
        <dl className="acp-liste">
          <Ligne libelle={T.catalogue.skillsInstallees}>
            <Donnee valeur={nombre(liste.length)} />
          </Ligne>
          <Ligne libelle={T.catalogue.skillsActivees}>
            <Donnee valeur={nombre(activees.length)} />
          </Ligne>
          <Ligne libelle={T.catalogue.skillsDesactivees}>
            <Donnee valeur={nombre(desactivees.length)} />
          </Ligne>
        </dl>
        <details className="acp-details">
          <summary>{T.catalogue.listeSkills}</summary>
          <ul className="acp-noms">
            {tries.map((s, rang) => (
              <li key={chaine(s.name) ?? String(rang)} className="acp-nom-etat">
                <Donnee valeur={chaine(s.name)} mono /> <Pastille etat={etat(s)} />
              </li>
            ))}
          </ul>
        </details>
      </div>
    );
  }
  return (
    <Carte titre={T.catalogue.vuParHermes} id="acp-catalogue-hermes">
      <p className="acp-discret">{T.catalogue.vuParHermesNote}</p>
      {contenu}
    </Carte>
  );
}

export function Catalogue(): Noeud {
  const catalogue = useChargement<DonneesCatalogue>(lireCatalogue);
  return (
    <div className="acp-page" data-acp-racine="catalogue">
      <div className="acp-entete">
        <h1 className="acp-titre">{T.catalogue.titre}</h1>
        <p className="acp-discret">{T.catalogue.intro}</p>
      </div>
      {catalogue.etat === "chargement" ? <EnChargement /> : null}
      {catalogue.etat === "erreur" ? <BlocErreur erreur={catalogue.erreur} message={T.catalogue.indisponible} /> : null}
      {catalogue.etat === "ok" ? <VueCatalogue donnees={catalogue.valeur} /> : null}
      <VueHermes />
    </div>
  );
}
