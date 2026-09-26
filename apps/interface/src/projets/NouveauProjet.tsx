// Vue « Nouveau projet » : POST /v1/projets (clé d'idempotence par envoi : un double appui ne lance
// qu'un projet). Les types de projet viennent du verrou du catalogue (/v1/catalogue), les dépôts et les
// modèles de l'inventaire du poste (/v1/poste) :
// - sans inventaire, le champ Dépôt est désactivé et le dit : seul « Sans dépôt » est possible (D25) ;
// - l'exploration (exécutant, modèle, effort) ne se choisit que si un relevé existe, et seulement parmi
//   ce qu'il contient, efforts interdits exclus ; un relevé factice est signalé comme tel ;
// - les refus de l'API s'affichent tels quels (message français du greffon).
import type * as ReactTypes from "react";
import { T } from "../chaines";
import { lireCatalogue } from "../api";
import { BlocErreur, Donnee, EnChargement, useChargement } from "../commun";
import { h, useState, type Noeud } from "../react";
import { chaine, listeDeChaines, type Catalogue } from "../types";
import { lancerProjet, lirePoste, nouvelleCle } from "./api";
import { Bouton, RetourEnvoi, type Naviguer } from "./briques";
import { useEnvoi } from "./envoi";
import { libelleProfil, libelleVoie } from "./libelles";
import type { CatalogueDuPoste, DemandeLancement, ReponseLancement, ReponsePoste, VoieReleve } from "./types";

type Evenement = ReactTypes.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>;
const valeurDe = (e: Evenement): string => e.target.value;

const PROFILS_CONNUS = ["base", "web", "recherche", "donnees"];

/** Voies relevées (un relevé, même périmé), dans l'ordre admis pour l'exploration par le greffon. */
export function voiesRelevees(catalogue: CatalogueDuPoste | null | undefined): string[] {
  const voies = catalogue?.voies && typeof catalogue.voies === "object" ? catalogue.voies : {};
  const ordre = listeDeChaines(catalogue?.politique?.voies_par_classe?.exploration);
  const candidates = ordre.length > 0 ? ordre : Object.keys(voies);
  return candidates.filter((v) => voies[v] && voies[v].etat !== "inconnu" && voies[v].releve_le);
}

/** Alias des dépôts autorisés, lus dans les relevés ; null si le poste n'a publié AUCUN relevé. */
export function depotsConnus(catalogue: CatalogueDuPoste | null | undefined): string[] | null {
  const voies = catalogue?.voies && typeof catalogue.voies === "object" ? catalogue.voies : {};
  const relevees = Object.values(voies).filter((v) => v && v.etat !== "inconnu" && v.releve_le);
  if (catalogue?.etat !== "connu" || relevees.length === 0) return null;
  const alias = new Set<string>();
  for (const v of relevees) for (const d of listeDeChaines(v.depots)) alias.add(d);
  return [...alias].sort();
}

/** Efforts relevés d'un modèle, moins les efforts interdits par la politique (D39). */
export function effortsAdmis(voie: VoieReleve | undefined, modele: string, interdits: string[]): string[] {
  const modeles = Array.isArray(voie?.modeles) ? voie.modeles : [];
  const choisi = modele ? modeles.find((m) => m.id === modele) : (modeles.find((m) => m.isDefault) ?? modeles[0]);
  return listeDeChaines(choisi?.supportedReasoningEfforts).filter((e) => !interdits.includes(e));
}

function Formulaire(props: {
  catalogue: Catalogue | null;
  poste: ReponsePoste | null;
  naviguer: Naviguer;
  apres: () => void;
}): Noeud {
  const cataloguePoste = props.poste?.catalogue ?? null;
  const depots = depotsConnus(cataloguePoste);
  const voies = voiesRelevees(cataloguePoste);
  const interdits = listeDeChaines(cataloguePoste?.politique?.efforts_interdits);
  const profils = (() => {
    const lus = props.catalogue?.profils && typeof props.catalogue.profils === "object"
      ? Object.keys(props.catalogue.profils) : [];
    return lus.length > 0 ? lus : PROFILS_CONNUS;
  })();

  const [titre, fixerTitre] = useState("");
  const [objectif, fixerObjectif] = useState("");
  const [profil, fixerProfil] = useState(profils.includes("base") ? "base" : (profils[0] ?? "base"));
  const [reponses, fixerReponses] = useState<DemandeLancement["reponses"]>("hermes_d_abord");
  const [depot, fixerDepot] = useState("");
  const [voie, fixerVoie] = useState(voies[0] ?? "");
  const [modele, fixerModele] = useState("");
  const [effort, fixerEffort] = useState("");
  const [cle, fixerCle] = useState(nouvelleCle);
  const envoi = useEnvoi<ReponseLancement>();

  const releveVoie: VoieReleve | undefined = voie ? cataloguePoste?.voies?.[voie] : undefined;
  const modeles = Array.isArray(releveVoie?.modeles) ? releveVoie.modeles.filter((m) => chaine(m.id)) : [];
  const efforts = effortsAdmis(releveVoie, modele, interdits);
  const avecExploration = depot !== "" && voies.length > 0;
  const complet = titre.trim() !== "" && objectif.trim() !== "";

  const lancer = async (evenement: ReactTypes.FormEvent) => {
    evenement.preventDefault();
    if (!complet) return;
    const demande: DemandeLancement = {
      titre: titre.trim(),
      objectif: objectif.trim(),
      profil,
      depot: depot || null,
      reponses,
    };
    if (avecExploration && voie) {
      demande.exploration = { voie, ...(modele ? { modele } : {}), ...(effort ? { effort } : {}) };
    }
    const resultat = await envoi.envoyer(() => lancerProjet(demande, cle));
    const id = chaine(resultat?.projet?.id);
    if (resultat !== null) {
      fixerCle(nouvelleCle());
      props.apres();
      if (id) props.naviguer({ genre: "detail", id });
    }
  };

  return (
    <form className="acp-formulaire" onSubmit={(e: ReactTypes.FormEvent) => void lancer(e)} aria-labelledby="acp-nouveau-titre">
      <div className="acp-champ">
        <label htmlFor="acp-projet-titre-champ">{T.projets.champTitre}</label>
        <input
          id="acp-projet-titre-champ"
          type="text"
          data-acp-donnee=""
          maxLength={120}
          required
          value={titre}
          onChange={(e: Evenement) => fixerTitre(valeurDe(e))}
        />
      </div>
      <div className="acp-champ">
        <label htmlFor="acp-projet-objectif">{T.projets.champObjectif}</label>
        <textarea
          id="acp-projet-objectif"
          data-acp-donnee=""
          rows={5}
          maxLength={4000}
          required
          aria-describedby="acp-projet-objectif-aide"
          value={objectif}
          onChange={(e: Evenement) => fixerObjectif(valeurDe(e))}
        />
        <p className="acp-discret" id="acp-projet-objectif-aide">
          {T.projets.aideObjectif}
        </p>
      </div>
      <div className="acp-champ">
        <label htmlFor="acp-projet-profil">{T.projets.champProfil}</label>
        <select id="acp-projet-profil" value={profil} onChange={(e: Evenement) => fixerProfil(valeurDe(e))}>
          {profils.map((p) =>
            libelleProfil(p) ? (
              <option key={p} value={p}>
                {libelleProfil(p)}
              </option>
            ) : (
              <option key={p} value={p} data-acp-donnee="">
                {p}
              </option>
            ),
          )}
        </select>
      </div>
      <fieldset className="acp-groupe-choix">
        <legend>{T.projets.champReponses}</legend>
        <label className="acp-choix-radio">
          <input
            type="radio"
            name="acp-projet-reponses"
            value="hermes_d_abord"
            checked={reponses === "hermes_d_abord"}
            onChange={() => fixerReponses("hermes_d_abord")}
          />
          <span>
            <span className="acp-choix-radio__titre">{T.projets.reponsesHermes}</span>
            <span className="acp-discret">{T.projets.reponsesHermesAide}</span>
          </span>
        </label>
        <label className="acp-choix-radio">
          <input
            type="radio"
            name="acp-projet-reponses"
            value="proprietaire"
            checked={reponses === "proprietaire"}
            onChange={() => fixerReponses("proprietaire")}
          />
          <span>
            <span className="acp-choix-radio__titre">{T.projets.reponsesProprietaire}</span>
            <span className="acp-discret">{T.projets.reponsesProprietaireAide}</span>
          </span>
        </label>
      </fieldset>
      <div className="acp-champ">
        <label htmlFor="acp-projet-depot">{T.projets.champDepot}</label>
        <select
          id="acp-projet-depot"
          value={depot}
          disabled={depots === null}
          aria-describedby={depots === null ? "acp-projet-depot-aide" : undefined}
          onChange={(e: Evenement) => fixerDepot(valeurDe(e))}
        >
          <option value="">{T.projets.sansDepot}</option>
          {(depots ?? []).map((d) => (
            <option key={d} value={d} data-acp-donnee="">
              {d}
            </option>
          ))}
        </select>
        {depots === null ? (
          <p className="acp-discret" id="acp-projet-depot-aide">
            {T.projets.aucunDepotConnu}
          </p>
        ) : null}
      </div>
      {cataloguePoste?.releve_factice === true ? (
        <p className="acp-alerte-texte" role="note">
          {T.projets.releveFactice}
        </p>
      ) : null}
      {avecExploration ? (
        <fieldset className="acp-groupe-choix">
          <legend>{T.projets.exploration}</legend>
          <p className="acp-discret">{T.projets.explorationAide}</p>
          <div className="acp-champ">
            <label htmlFor="acp-projet-voie">{T.projets.champVoie}</label>
            <select
              id="acp-projet-voie"
              value={voie}
              onChange={(e: Evenement) => {
                fixerVoie(valeurDe(e));
                fixerModele("");
                fixerEffort("");
              }}
            >
              {voies.map((v) =>
                libelleVoie(v) ? (
                  <option key={v} value={v}>
                    {libelleVoie(v)}
                  </option>
                ) : (
                  <option key={v} value={v} data-acp-donnee="">
                    {v}
                  </option>
                ),
              )}
            </select>
          </div>
          <div className="acp-champ">
            <label htmlFor="acp-projet-modele">{T.projets.champModele}</label>
            <select
              id="acp-projet-modele"
              value={modele}
              onChange={(e: Evenement) => {
                fixerModele(valeurDe(e));
                fixerEffort("");
              }}
            >
              <option value="">{T.projets.modeleParDefaut}</option>
              {modeles.map((m) => (
                <option key={String(m.id)} value={String(m.id)} data-acp-donnee="">
                  {String(m.id)}
                </option>
              ))}
            </select>
          </div>
          <div className="acp-champ">
            <label htmlFor="acp-projet-effort">{T.projets.champEffort}</label>
            <select id="acp-projet-effort" value={effort} onChange={(e: Evenement) => fixerEffort(valeurDe(e))}>
              <option value="">{T.projets.effortParDefaut}</option>
              {efforts.map((x) => (
                <option key={x} value={x} data-acp-donnee="">
                  {x}
                </option>
              ))}
            </select>
          </div>
          <p className="acp-discret">
            <span>{T.projets.releveDu}</span> <Donnee valeur={chaine(releveVoie?.releve_le_lisible)} />
          </p>
          {releveVoie?.perime === true ? <p className="acp-alerte-texte">{T.projets.relevePerime}</p> : null}
        </fieldset>
      ) : null}
      <div className="acp-actions">
        <Bouton
          type="submit"
          principal
          libelle={envoi.etat.etat === "envoi" ? T.projets.envoi : T.projets.lancer}
          desactive={!complet || envoi.etat.etat === "envoi"}
        />
      </div>
      <RetourEnvoi etat={envoi.etat} />
    </form>
  );
}

export function NouveauProjet(props: { naviguer: Naviguer; apres: () => void }): Noeud {
  const catalogue = useChargement<Catalogue>(lireCatalogue);
  const poste = useChargement<ReponsePoste>(lirePoste);
  const pret = catalogue.etat !== "chargement" && poste.etat !== "chargement";
  return (
    <section className="acp-carte" aria-labelledby="acp-nouveau-titre">
      <h2 className="acp-carte__titre" id="acp-nouveau-titre">
        {T.projets.nouveauTitre}
      </h2>
      <p className="acp-discret">{T.projets.nouveauIntro}</p>
      {!pret ? <EnChargement /> : null}
      {poste.etat === "erreur" ? <BlocErreur erreur={poste.erreur} message={T.projets.posteIndisponible} /> : null}
      {catalogue.etat === "erreur" ? <BlocErreur erreur={catalogue.erreur} message={T.catalogue.indisponible} /> : null}
      {pret ? (
        <Formulaire
          catalogue={catalogue.etat === "ok" ? catalogue.valeur : null}
          poste={poste.etat === "ok" ? poste.valeur : null}
          naviguer={props.naviguer}
          apres={props.apres}
        />
      ) : null}
    </section>
  );
}

