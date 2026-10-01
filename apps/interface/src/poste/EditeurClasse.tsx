// Éditeur d'une classe de la table de routage : entrées ordonnées, listes déroulantes alimentées SEULEMENT par le
// relevé (modèles de la voie, efforts pris en charge, paliers admis par Hermes), verdict du greffon pour chaque
// entrée enregistrée (admise, ou le refus tel quel), suggestion calculée sur les champs lus.
import { T } from "../chaines";
import { Donnee } from "../commun";
import { h, type Noeud } from "../react";
import { Bouton, Etiquette } from "../projets/briques";
import { libelleClasse, libelleEtatTable, libelleVoie } from "./libelles";
import type { ClasseRoutage, Entree, ModeleReleve, VoieCatalogue } from "./types";

export interface ContexteEditeur {
  voies: Record<string, VoieCatalogue>;
  paliers: string[];
}

function modelesDe(contexte: ContexteEditeur, voie: string | undefined): ModeleReleve[] {
  const cle = voie === "hermes" ? "poste-codex" : voie;
  const modeles = cle ? contexte.voies[cle]?.modeles : undefined;
  return Array.isArray(modeles) ? modeles : [];
}

/** Un modèle du relevé est-il marqué par défaut ? Jamais pour Claude (isDefault nul, D59) : sans lui, le serveur
 *  refuse une entrée sans modèle ; la liste n'offre alors pas « Modèle par défaut du relevé » (D73). */
function avecModeleParDefaut(modeles: ModeleReleve[]): boolean {
  return modeles.some((m) => m.isDefault === true);
}

function effortsDe(contexte: ContexteEditeur, entree: Entree): string[] {
  if (entree.voie === "hermes") return [];
  const modele = modelesDe(contexte, entree.voie).find((m) => m.id === entree.modele);
  return Array.isArray(modele?.supportedReasoningEfforts) ? modele.supportedReasoningEfforts : [];
}

function LigneEntree(props: {
  classe: string;
  rang: number;
  entree: Entree;
  voies: string[];
  contexte: ContexteEditeur;
  changer: (entree: Entree) => void;
  retirer: () => void;
}): Noeud {
  const { classe, rang, entree, contexte } = props;
  const id = `acp-routage-${classe}-${rang}`;
  const modeles = modelesDe(contexte, entree.voie);
  const efforts = effortsDe(contexte, entree);
  const hermes = entree.voie === "hermes";
  const choixExige = !hermes && !avecModeleParDefaut(modeles);
  return (
    <div className="acp-entree-routage" role="group" aria-labelledby={`${id}-titre`}>
      <p className="acp-discret" id={`${id}-titre`}>
        <span>{T.poste.rang}</span> <Donnee valeur={rang + 1} />
      </p>
      <div className="acp-champ">
        <label htmlFor={`${id}-voie`}>{T.poste.champVoie}</label>
        <select id={`${id}-voie`} value={entree.voie ?? ""}
                onChange={(e) => props.changer({ voie: e.currentTarget.value, modele: null, effort: null,
                                                  palier: entree.palier ?? null })}>
          {props.voies.map((v) => (
            <option key={v} value={v} data-acp-donnee={libelleVoie(v) ? undefined : ""}>
              {libelleVoie(v) ?? v}
            </option>
          ))}
        </select>
      </div>
      <div className="acp-champ">
        <label htmlFor={`${id}-modele`}>{T.poste.champModele}</label>
        <select id={`${id}-modele`} value={entree.modele ?? ""}
                onChange={(e) => props.changer({ ...entree, modele: e.currentTarget.value || null, effort: null })}>
          <option value="" disabled={choixExige}>
            {hermes ? T.poste.modeleDuProfil : choixExige ? T.poste.modeleAChoisir : T.poste.modeleParDefaut}
          </option>
          {modeles.map((m) => (
            <option key={m.id} value={m.id} data-acp-donnee="">
              {m.id}
            </option>
          ))}
        </select>
      </div>
      <div className="acp-champ">
        <label htmlFor={`${id}-effort`}>{T.poste.champEffort}</label>
        <select id={`${id}-effort`} value={entree.effort ?? ""}
                onChange={(e) => props.changer({ ...entree, effort: e.currentTarget.value || null })}>
          <option value="">{T.poste.effortParDefaut}</option>
          {efforts.map((effort) => (
            <option key={effort} value={effort} data-acp-donnee="">
              {effort}
            </option>
          ))}
        </select>
      </div>
      <div className="acp-champ">
        <label htmlFor={`${id}-palier`}>{T.poste.champPalier}</label>
        <select id={`${id}-palier`} value={entree.palier ?? ""}
                onChange={(e) => props.changer({ ...entree, palier: e.currentTarget.value || null })}>
          <option value="">{T.poste.palierStandard}</option>
          {contexte.paliers.filter((p) => p !== "default").map((p) => (
            <option key={p} value={p} data-acp-donnee="">
              {p}
            </option>
          ))}
        </select>
      </div>
      <div className="acp-actions">
        <Bouton libelle={T.poste.retirer} surClic={props.retirer} />
      </div>
    </div>
  );
}

export function EditeurClasse(props: {
  classe: string;
  vue: ClasseRoutage;
  brouillon: Entree[];
  contexte: ContexteEditeur;
  changer: (entrees: Entree[]) => void;
}): Noeud {
  const { classe, vue, brouillon } = props;
  const voies = Array.isArray(vue.voies) ? vue.voies : [];
  const suggestion = vue.suggestion ?? {};
  const jugees = Array.isArray(vue.entrees) ? vue.entrees : [];
  const id = `acp-routage-${classe}`;
  return (
    <section className="acp-carte" aria-labelledby={id}>
      <h3 className="acp-carte__titre" id={id}>
        {libelleClasse(classe) ?? classe}
      </h3>
      <p className="acp-etat">
        <Etiquette libelle={libelleEtatTable(vue.etat)} brut={vue.etat} />
      </p>
      {jugees.length > 0 ? (
        <ul className="acp-liste">
          {jugees.map((e, i) => (
            <li key={i} className="acp-groupe">
              <span className="acp-etat">
                <span className={`acp-pastille acp-pastille--${e.admise ? "succes" : "echec"}`}>
                  {e.admise ? T.poste.entreeAdmise : T.poste.entreeRefusee}
                </span>
                <Donnee valeur={[e.voie, e.modele, e.effort, e.palier].filter(Boolean).join(" · ")} mono />
              </span>
              {!e.admise && e.message ? <Donnee valeur={e.message} /> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="acp-discret">{T.poste.aucuneEntree}</p>
      )}
      {brouillon.map((entree, rang) => (
        <LigneEntree key={rang} classe={classe} rang={rang} entree={entree} voies={voies} contexte={props.contexte}
                     changer={(nouvelle) => props.changer(brouillon.map((e, i) => (i === rang ? nouvelle : e)))}
                     retirer={() => props.changer(brouillon.filter((_e, i) => i !== rang))} />
      ))}
      <div className="acp-actions">
        <Bouton libelle={T.poste.ajouterEntree} desactive={voies.length === 0 || brouillon.length >= 8}
                surClic={() => props.changer([...brouillon, { voie: voies[0], modele: null, effort: null,
                                                               palier: null }])} />
        {Array.isArray(suggestion.entrees) && suggestion.entrees.length > 0 ? (
          <Bouton libelle={T.poste.appliquerSuggestion}
                  surClic={() => props.changer((suggestion.entrees ?? []).map((e) => ({ ...e })))} />
        ) : null}
      </div>
      {suggestion.libelle ? (
        <p className="acp-discret">
          <Donnee valeur={suggestion.libelle} />
        </p>
      ) : null}
      {(suggestion.remarques ?? []).map((r, i) => (
        <p key={i} className="acp-discret">
          <Donnee valeur={r} />
        </p>
      ))}
    </section>
  );
}
