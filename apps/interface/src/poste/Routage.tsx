// Vue « Routage » (cahier P5 § 13.2) : listes relevées par voie (badge « Relevé du compte », « Liste de secours »,
// « Alias documentés », « Périmé », « Inconnu »…), table de routage par classe (éditeur, suggestion, verdict du
// greffon pour chaque entrée, validation complète ou rien), interdits côté Hermes, interdits du poste en lecture
// seule, surcharges globales, « Accepter ce relevé comme celui de mon compte ». Les refus de l'API sont rendus tels
// quels, entrée par entrée.
import { T } from "../chaines";
import { BlocErreur, Carte, Donnee, EnChargement, Ligne } from "../commun";
import { h, useState, type Noeud } from "../react";
import { Bouton, Etiquette, Horodatage, RetourEnvoi } from "../projets/briques";
import { useEnvoi } from "../projets/envoi";
import { useSondage } from "../projets/sondage";
import { accepterReleve, lireRoutage, refusDeLaTable, validerTable } from "./api";
import { EditeurClasse } from "./EditeurClasse";
import { libelleBadge, libelleClasse, libelleVoie } from "./libelles";
import { PolitiqueDuPoste, PolitiqueHermes } from "./Politique";
import { Surcharges } from "./Surcharges";
import type { Entree, ResolutionObservee, VoieCatalogue, VueRoutage } from "./types";

function Liste(props: { voie: string; catalogue: VoieCatalogue | undefined; apres: () => void }): Noeud {
  const c = props.catalogue;
  const envoi = useEnvoi();
  const modeles = Array.isArray(c?.modeles) ? c.modeles : [];
  const accepter = async () => {
    if (typeof c?.releve_id !== "number") return;
    const fait = await envoi.envoyer(() => accepterReleve(c.releve_id as number));
    if (fait) props.apres();
  };
  const id = `acp-routage-liste-${props.voie}`;
  return (
    <section className="acp-carte" aria-labelledby={id}>
      <h3 className="acp-carte__titre" id={id}>
        {libelleVoie(props.voie) ?? props.voie}
      </h3>
      <p className="acp-etat">
        <Etiquette libelle={libelleBadge(c?.badge)} brut={c?.badge} />
        {c?.releve_le ? <Horodatage valeur={c.releve_le} /> : null}
        {c?.version_cli ? <Donnee valeur={c.version_cli} mono /> : null}
      </p>
      {c?.detail ? (
        <p>
          <Donnee valeur={c.detail} />
        </p>
      ) : null}
      {c?.documentation_lue_le ? (
        <p className="acp-discret">
          <Donnee valeur={c.documentation_lue_le} mono />
        </p>
      ) : null}
      {modeles.length === 0 ? (
        <p className="acp-discret">{!c || c.badge === "inconnu" ? T.poste.aucunReleve : T.poste.aucunModele}</p>
      ) : (
        <ul className="acp-liste">
          {modeles.map((m) => (
            <li key={m.id} className="acp-groupe">
              <span className="acp-etat">
                <Donnee valeur={m.id} mono />
                {m.isDefault === true ? <span className="acp-pastille acp-pastille--actif">{T.poste.parDefaut}</span> : null}
              </span>
              <span className="acp-discret">
                <span>{T.poste.efforts}</span>{" "}
                {Array.isArray(m.supportedReasoningEfforts) && m.supportedReasoningEfforts.length === 0 ? (
                  <span>{T.poste.aucunEffort}</span>
                ) : Array.isArray(m.supportedReasoningEfforts) ? (
                  <Donnee valeur={m.supportedReasoningEfforts.join(", ")} mono />
                ) : (
                  <span>{T.poste.effortsInconnus}</span>
                )}
              </span>
              {m.resolution_documentee ? (
                <span className="acp-discret">
                  <span>{T.poste.resolution}</span> <Donnee valeur={m.resolution_documentee} mono />
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {c?.badge === "liste_de_secours_probable" && typeof c.releve_id === "number" ? (
        <div className="acp-groupe">
          <p className="acp-discret" id={`${id}-accepter`}>
            {T.poste.accepterAide}
          </p>
          <div className="acp-actions">
            <Bouton libelle={T.poste.accepterReleve} surClic={accepter} desactive={envoi.etat.etat === "envoi"}
                    decritPar={`${id}-accepter`} />
          </div>
          <RetourEnvoi etat={envoi.etat} reussite={T.poste.releveAccepte} />
        </div>
      ) : null}
    </section>
  );
}

function brouillonDepuis(vue: VueRoutage): Record<string, Entree[]> {
  const brouillon: Record<string, Entree[]> = {};
  for (const [classe, c] of Object.entries(vue.classes ?? {})) {
    brouillon[classe] = (c.entrees ?? []).map((e) => ({ voie: e.voie, modele: e.modele ?? null, effort: e.effort ?? null,
                                                        palier: e.palier ?? null }));
  }
  return brouillon;
}

function Table(props: { vue: VueRoutage; apres: () => void }): Noeud {
  const [brouillon, fixerBrouillon] = useState<Record<string, Entree[]>>(() => brouillonDepuis(props.vue));
  const envoi = useEnvoi<VueRoutage>();
  const contexte = { voies: props.vue.voies ?? {}, paliers: props.vue.politique_hermes?.paliers_admis ?? [] };
  const valider = async () => {
    const classes: Record<string, Entree[]> = {};
    for (const [classe, entrees] of Object.entries(brouillon)) if (entrees.length > 0) classes[classe] = entrees;
    const vue = await envoi.envoyer(() => validerTable(props.vue.releves ?? {}, classes));
    if (vue) {
      fixerBrouillon(brouillonDepuis(vue));
      props.apres();
    }
  };
  const refus = envoi.etat.etat === "erreur" ? refusDeLaTable(envoi.etat.erreur.detail) : [];
  const vide = Object.values(brouillon).every((e) => e.length === 0);
  return (
    <Carte titre={T.poste.tableTitre} id="acp-poste-table">
      <div className="acp-sections">
        {Object.entries(props.vue.classes ?? {}).map(([classe, c]) => (
          <EditeurClasse key={classe} classe={classe} vue={c} brouillon={brouillon[classe] ?? []} contexte={contexte}
                         changer={(entrees) => fixerBrouillon((avant) => ({ ...avant, [classe]: entrees }))} />
        ))}
      </div>
      <div className="acp-actions">
        <Bouton libelle={T.poste.validerTable} principal surClic={valider} desactive={envoi.etat.etat === "envoi" || vide} />
      </div>
      <RetourEnvoi etat={envoi.etat} reussite={T.poste.tableValidee} />
      {refus.length > 0 ? (
        <div className="acp-erreur" role="alert">
          <p>{T.poste.refusDeLaTable}</p>
          <ul className="acp-liste">
            {refus.map((r, i) => (
              <li key={i}>
                <Donnee valeur={libelleClasse(r.classe) ?? r.classe} /> <span>{T.poste.rang}</span>{" "}
                <Donnee valeur={typeof r.rang === "number" ? r.rang + 1 : null} /> <Donnee valeur={r.message} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Carte>
  );
}

/** Étape P6 : modèle servi observé par alias (jamais supposé : vide tant qu'aucune carte n'est terminée). */
function Resolutions(props: { resolutions: ResolutionObservee[] }): Noeud {
  return (
    <Carte titre={T.poste.resolutionsTitre} id="acp-poste-resolutions">
      <p className="acp-discret">{T.poste.resolutionsAide}</p>
      {props.resolutions.length === 0 ? (
        <p className="acp-discret">{T.poste.aucuneResolution}</p>
      ) : (
        props.resolutions.map((r, rang) => (
          <dl key={`${r.voie ?? ""}-${r.alias ?? rang}`} className="acp-liste">
            <Ligne libelle={T.poste.executant.voie}>
              <Donnee valeur={r.voie} mono />
            </Ligne>
            <Ligne libelle={T.poste.aliasObserve}>
              <Donnee valeur={r.alias} mono />
            </Ligne>
            <Ligne libelle={T.poste.executant.modeleServi}>
              <Donnee valeur={r.modele_servi} mono />
            </Ligne>
            <Ligne libelle={T.poste.observeeLe}>
              <Horodatage valeur={r.observe_le} />
            </Ligne>
          </dl>
        ))
      )}
    </Carte>
  );
}

export function Routage(props: { jeton: number; apres: () => void }): Noeud {
  const lecture = useSondage(lireRoutage, props.jeton);
  const vue = lecture.valeur;
  if (vue === null) {
    return lecture.erreur === null ? <EnChargement /> : <BlocErreur erreur={lecture.erreur} message={T.poste.indisponible} />;
  }
  const voies = vue.voies ?? {};
  // La table n'est remontée (brouillon relu) que si un nouveau relevé arrive : ni à chaque sondage, ni après un geste
  // (le retour du geste resterait sinon invisible).
  const cleTable = JSON.stringify(vue.releves ?? {});
  return (
    <div className="acp-sections">
      {lecture.erreur !== null ? (
        <p className="acp-alerte-texte" role="status">
          {T.poste.actualisationImpossible}
        </p>
      ) : null}
      <p className="acp-discret">{T.poste.routageIntro}</p>
      <Carte titre={T.poste.listesTitre} id="acp-poste-listes">
        <div className="acp-grille">
          {["poste-codex", "poste-claude"].map((voie) => (
            <Liste key={voie} voie={voie} catalogue={voies[voie]} apres={props.apres} />
          ))}
        </div>
      </Carte>
      <Resolutions resolutions={Array.isArray(vue.resolutions_observees) ? vue.resolutions_observees : []} />
      <Table key={cleTable} vue={vue} apres={props.apres} />
      <PolitiqueHermes vue={vue} apres={props.apres} />
      <PolitiqueDuPoste politique={vue.politique_poste} />
      <Surcharges vue={vue} apres={props.apres} />
    </div>
  );
}
