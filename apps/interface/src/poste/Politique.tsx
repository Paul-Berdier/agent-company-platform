// Interdits CÔTÉ HERMES (efforts interdits, paliers admis), levés seulement avec la phrase de confirmation exacte
// quand c'est une dépense hors enveloppe ; et, en lecture seule, ce que poste.toml interdit (« Interdit par le
// poste » : seule une modification locale sur le PC peut le lever).
import { T } from "../chaines";
import { Carte, Donnee, Ligne } from "../commun";
import { h, useState, type Noeud } from "../react";
import { Bouton, RetourEnvoi } from "../projets/briques";
import { useEnvoi } from "../projets/envoi";
import { poserPolitique } from "./api";
import type { PolitiquePoste, VueRoutage } from "./types";

function liste(texte: string): string[] {
  return texte.split(",").map((v) => v.trim()).filter(Boolean);
}

function Valeurs(props: { valeurs: unknown; vide?: string }): Noeud {
  const valeurs = Array.isArray(props.valeurs) ? props.valeurs.filter((v) => typeof v === "string") : null;
  if (valeurs === null) return <Donnee valeur={null} />;
  if (valeurs.length === 0) return props.vide ? <span>{props.vide}</span> : <Donnee valeur={null} />;
  return <Donnee valeur={valeurs.join(", ")} mono />;
}

export function PolitiqueHermes(props: { vue: VueRoutage; apres: () => void }): Noeud {
  const politique = props.vue.politique_hermes ?? {};
  const [efforts, fixerEfforts] = useState(() => (politique.efforts_interdits ?? []).join(", "));
  const [paliers, fixerPaliers] = useState(() => (politique.paliers_admis ?? []).join(", "));
  const [motif, fixerMotif] = useState("");
  const [phrase, fixerPhrase] = useState("");
  const envoi = useEnvoi();
  const envoyer = async (evenement: { preventDefault: () => void }) => {
    evenement.preventDefault();
    const fait = await envoi.envoyer(() => poserPolitique({
      efforts_interdits: liste(efforts), paliers_admis: liste(paliers), motif, confirmation: phrase.trim() || null }));
    if (fait) props.apres();
  };
  return (
    <Carte titre={T.poste.politiqueTitre} id="acp-poste-politique">
      <p className="acp-discret" id="acp-poste-politique-aide">
        {T.poste.politiqueAide}
      </p>
      <dl className="acp-liste">
        <Ligne libelle={T.poste.phraseAttendue}>
          <Donnee valeur={politique.confirmation} />
        </Ligne>
      </dl>
      <form className="acp-formulaire" onSubmit={envoyer}>
        <div className="acp-champ">
          <label htmlFor="acp-poste-efforts">{T.poste.effortsInterdits}</label>
          <input id="acp-poste-efforts" value={efforts} aria-describedby="acp-poste-liste-aide"
                 onChange={(e) => fixerEfforts(e.currentTarget.value)} />
        </div>
        <div className="acp-champ">
          <label htmlFor="acp-poste-paliers">{T.poste.paliersAdmis}</label>
          <input id="acp-poste-paliers" value={paliers} aria-describedby="acp-poste-liste-aide"
                 onChange={(e) => fixerPaliers(e.currentTarget.value)} />
        </div>
        <p className="acp-discret" id="acp-poste-liste-aide">
          {T.poste.separateurListe}
        </p>
        <div className="acp-champ">
          <label htmlFor="acp-poste-politique-motif">{T.poste.champMotif}</label>
          <input id="acp-poste-politique-motif" value={motif} maxLength={200}
                 onChange={(e) => fixerMotif(e.currentTarget.value)} />
        </div>
        <div className="acp-champ">
          <label htmlFor="acp-poste-phrase">{T.poste.phrase}</label>
          <input id="acp-poste-phrase" value={phrase} autoComplete="off" aria-describedby="acp-poste-politique-aide"
                 onChange={(e) => fixerPhrase(e.currentTarget.value)} />
        </div>
        <div className="acp-actions">
          <Bouton type="submit" libelle={T.poste.enregistrerPolitique}
                  desactive={envoi.etat.etat === "envoi" || !motif.trim()} />
        </div>
      </form>
      <RetourEnvoi etat={envoi.etat} reussite={T.poste.politiqueEnregistree} />
    </Carte>
  );
}

export function PolitiqueDuPoste(props: { politique: PolitiquePoste | null | undefined }): Noeud {
  const p = props.politique;
  return (
    <Carte titre={T.poste.politiquePosteTitre} id="acp-poste-politique-poste">
      <p className="acp-discret">{T.poste.politiquePosteAide}</p>
      <dl className="acp-liste">
        <Ligne libelle={T.poste.executants}>
          <Valeurs valeurs={p?.executants} />
        </Ligne>
        <Ligne libelle={T.poste.effortsInterdits}>
          <Valeurs valeurs={p?.efforts_interdits} />
        </Ligne>
        <Ligne libelle={T.poste.paliersAdmis}>
          <Valeurs valeurs={p?.paliers_admis} />
        </Ligne>
        <Ligne libelle={T.poste.modelesPermis}>
          <Valeurs valeurs={p?.modeles_codex_permis} vide={T.poste.tousDuReleve} />
        </Ligne>
        <Ligne libelle={T.poste.aliasPermis}>
          <Valeurs valeurs={p?.alias_claude_permis} />
        </Ligne>
        <Ligne libelle={T.poste.reseauExecutants}>
          {typeof p?.reseau_executants === "boolean" ? (
            <span>{p.reseau_executants ? T.commun.oui : T.commun.non}</span>
          ) : (
            <Donnee valeur={null} />
          )}
        </Ligne>
      </dl>
    </Carte>
  );
}
