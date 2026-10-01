// Surcharges GLOBALES (portée globale : P4 renvoyait leur création ici) : liste des actives, désactivation, création
// vérifiée par le greffon comme une entrée de la table (refus rendu tel quel).
import { T } from "../chaines";
import { Carte, Donnee } from "../commun";
import { h, useState, type Noeud } from "../react";
import { Bouton, Horodatage, RetourEnvoi } from "../projets/briques";
import { useEnvoi } from "../projets/envoi";
import { creerSurcharge, desactiverSurcharge } from "./api";
import { libelleClasse, libelleVoie } from "./libelles";
import type { VueRoutage } from "./types";

export function Surcharges(props: { vue: VueRoutage; apres: () => void }): Noeud {
  const surcharges = Array.isArray(props.vue.surcharges) ? props.vue.surcharges : [];
  const classes = Object.keys(props.vue.classes ?? {});
  const [classe, fixerClasse] = useState(() => classes[0] ?? "");
  const voies = props.vue.classes?.[classe]?.voies ?? [];
  const [voie, fixerVoie] = useState<string>("");
  const [modele, fixerModele] = useState("");
  const [effort, fixerEffort] = useState("");
  const [motif, fixerMotif] = useState("");
  const creation = useEnvoi();
  const desactivation = useEnvoi();
  const voieChoisie = voie && voies.includes(voie) ? voie : voies[0] ?? "";
  const envoyer = async (evenement: { preventDefault: () => void }) => {
    evenement.preventDefault();
    const fait = await creation.envoyer(() => creerSurcharge({
      classe, voie: voieChoisie, modele: modele.trim() || null, effort: effort.trim() || null, palier: null, motif }));
    if (fait) props.apres();
  };
  const desactiver = async (id: number) => {
    const fait = await desactivation.envoyer(() => desactiverSurcharge(id));
    if (fait) props.apres();
  };
  return (
    <Carte titre={T.poste.surchargesTitre} id="acp-poste-surcharges">
      <p className="acp-discret">{T.poste.surchargesAide}</p>
      {surcharges.length === 0 ? (
        <p className="acp-discret">{T.poste.aucuneSurcharge}</p>
      ) : (
        <ul className="acp-liste">
          {surcharges.map((s) => (
            <li key={s.id} className="acp-groupe">
              <span className="acp-etat">
                <Donnee valeur={libelleClasse(s.classe) ?? s.classe} />
                <Donnee valeur={[s.voie, s.modele, s.effort, s.palier].filter(Boolean).join(" · ")} mono />
                <Horodatage valeur={s.cree_le} />
              </span>
              <Donnee valeur={s.motif} />
              <div className="acp-actions">
                <Bouton libelle={T.poste.desactiver} surClic={() => desactiver(Number(s.id))}
                        desactive={desactivation.etat.etat === "envoi"} />
              </div>
            </li>
          ))}
        </ul>
      )}
      <RetourEnvoi etat={desactivation.etat} reussite={T.poste.surchargeDesactivee} />
      <form className="acp-formulaire" onSubmit={envoyer}>
        <div className="acp-champ">
          <label htmlFor="acp-surcharge-classe">{T.poste.classe}</label>
          <select id="acp-surcharge-classe" value={classe} onChange={(e) => fixerClasse(e.currentTarget.value)}>
            {classes.map((c) => (
              <option key={c} value={c} data-acp-donnee={libelleClasse(c) ? undefined : ""}>
                {libelleClasse(c) ?? c}
              </option>
            ))}
          </select>
        </div>
        <div className="acp-champ">
          <label htmlFor="acp-surcharge-voie">{T.poste.champVoie}</label>
          <select id="acp-surcharge-voie" value={voieChoisie} onChange={(e) => fixerVoie(e.currentTarget.value)}>
            {voies.map((v) => (
              <option key={v} value={v} data-acp-donnee={libelleVoie(v) ? undefined : ""}>
                {libelleVoie(v) ?? v}
              </option>
            ))}
          </select>
        </div>
        <div className="acp-champ">
          <label htmlFor="acp-surcharge-modele">{T.poste.champModele}</label>
          <input id="acp-surcharge-modele" value={modele} onChange={(e) => fixerModele(e.currentTarget.value)} />
        </div>
        <div className="acp-champ">
          <label htmlFor="acp-surcharge-effort">{T.poste.champEffort}</label>
          <input id="acp-surcharge-effort" value={effort} onChange={(e) => fixerEffort(e.currentTarget.value)} />
        </div>
        <div className="acp-champ">
          <label htmlFor="acp-surcharge-motif">{T.poste.champMotif}</label>
          <input id="acp-surcharge-motif" value={motif} maxLength={200} onChange={(e) => fixerMotif(e.currentTarget.value)} />
        </div>
        <div className="acp-actions">
          <Bouton type="submit" libelle={T.poste.creerSurcharge}
                  desactive={creation.etat.etat === "envoi" || !motif.trim() || !classe || !voieChoisie} />
        </div>
      </form>
      <RetourEnvoi etat={creation.etat} reussite={T.poste.surchargeCreee} />
    </Carte>
  );
}
