// Vue « Quotas » (cahier P5 § 12.5, § 13.2) : jauges par compteur (part utilisée, ligne du seuil du routage, remise
// à zéro en heure de Paris, offre, limite atteinte), état du relevé (Relevé, Périmé, Inconnu), source des quotas
// Claude (déclarée), Hermes (« Même enveloppe que Codex » seulement si poste.toml le déclare) ; « Relever
// maintenant ». Rien n'est estimé : une valeur absente reste « Inconnu ».
import { T } from "../chaines";
import { BlocErreur, Carte, Donnee, EnChargement, Ligne } from "../commun";
import { h, type Noeud } from "../react";
import { Bouton, Etiquette, Horodatage, RetourEnvoi } from "../projets/briques";
import { useEnvoi } from "../projets/envoi";
import { useDonnees } from "../donnees";
import { lireQuotas, releverMaintenant } from "./api";
import { libelleEtatQuotas, libelleVoie } from "./libelles";
import type { CompteurQuota, FenetreQuota, QuotasVoie } from "./types";

function pourcentage(valeur: unknown): number | null {
  return typeof valeur === "number" && Number.isFinite(valeur) && valeur >= 0 && valeur <= 100 ? valeur : null;
}

/** Jauge d'une fenêtre : part utilisée (barre), ligne du seuil ; valeur absente : barre vide et « Inconnu ». */
export function Jauge(props: { fenetre: FenetreQuota; seuil: number | null; id: string }): Noeud {
  const utilise = pourcentage(props.fenetre.used_percent);
  const seuil = pourcentage(props.seuil);
  const depasse = utilise !== null && seuil !== null && utilise >= seuil;
  return (
    <div className="acp-jauge-bloc">
      <p className="acp-etat">
        <span className="acp-discret">{T.poste.fenetre}</span> <Donnee valeur={props.fenetre.key} mono />
        {typeof props.fenetre.window_minutes === "number" ? (
          <span>
            <Donnee valeur={props.fenetre.window_minutes} /> <span>{T.poste.minutes}</span>
          </span>
        ) : null}
      </p>
      <div className={depasse ? "acp-jauge acp-jauge--depasse" : "acp-jauge"} role="meter" aria-labelledby={props.id}
           aria-valuemin={0} aria-valuemax={100} aria-valuenow={utilise ?? undefined}>
        <span className="acp-jauge__plein" style={{ width: `${utilise ?? 0}%` }} />
        {seuil !== null ? <span className="acp-jauge__seuil" style={{ left: `${seuil}%` }} /> : null}
      </div>
      <dl className="acp-liste">
        <Ligne libelle={T.poste.utilise}>
          <span id={props.id}>
            <Donnee valeur={utilise === null ? null : `${utilise} %`} />
          </span>
        </Ligne>
        <Ligne libelle={T.poste.restant}>
          <Donnee valeur={pourcentage(props.fenetre.remaining_percent) === null ? null
            : `${props.fenetre.remaining_percent} %`} />
        </Ligne>
        <Ligne libelle={T.poste.remiseAZero}>
          <Horodatage valeur={props.fenetre.resets_at} />
        </Ligne>
      </dl>
    </div>
  );
}

function Compteur(props: { compteur: CompteurQuota; seuil: number | null; prefixe: string }): Noeud {
  const c = props.compteur;
  const fenetres = Array.isArray(c.windows) ? c.windows : [];
  return (
    <div className="acp-groupe">
      <p className="acp-etat">
        <span className="acp-discret">{T.poste.compteur}</span> <Donnee valeur={c.limit_id} mono />
        {c.limit_reached === true ? <span className="acp-pastille acp-pastille--echec">{T.poste.limiteAtteinte}</span> : null}
      </p>
      <dl className="acp-liste">
        <Ligne libelle={T.poste.offre}>
          <Donnee valeur={c.plan} mono />
        </Ligne>
        <Ligne libelle={T.poste.releveLe}>
          <Horodatage valeur={c.observed_at} />
        </Ligne>
      </dl>
      {c.status !== "ok" && c.detail ? (
        <p>
          <Donnee valeur={c.detail} />
        </p>
      ) : null}
      {fenetres.map((f, i) => (
        <Jauge key={`${f.key ?? i}`} fenetre={f} seuil={props.seuil} id={`${props.prefixe}-${c.limit_id ?? "c"}-${i}`} />
      ))}
    </div>
  );
}

function Voie(props: { voie: string; quotas: QuotasVoie | undefined }): Noeud {
  const q = props.quotas ?? {};
  const compteurs = Array.isArray(q.compteurs) ? q.compteurs : [];
  const seuil = typeof q.seuil_pct === "number" ? q.seuil_pct : null;
  const id = `acp-quotas-${props.voie}`;
  return (
    <Carte titre={libelleVoie(props.voie) ?? props.voie} id={id}>
      <p className="acp-etat">
        <Etiquette libelle={libelleEtatQuotas(q.etat)} brut={q.etat} />
        {q.releve_le ? <Horodatage valeur={q.releve_le} /> : null}
      </p>
      <dl className="acp-liste">
        <Ligne libelle={T.poste.seuil}>
          <Donnee valeur={seuil === null ? null : `${seuil} %`} />
        </Ligne>
      </dl>
      {q.source_libelle ? (
        <p className="acp-discret">
          <Donnee valeur={q.source_libelle} />
        </p>
      ) : null}
      {q.detail ? (
        <p>
          <Donnee valeur={q.detail} />
        </p>
      ) : null}
      {compteurs.length === 0 ? (
        <p className="acp-discret">{T.poste.aucunCompteur}</p>
      ) : (
        compteurs.map((c, i) => <Compteur key={`${c.limit_id ?? i}`} compteur={c} seuil={seuil} prefixe={id} />)
      )}
    </Carte>
  );
}

export function Quotas(props: { jeton: number; apres: () => void }): Noeud {
  const lecture = useDonnees(lireQuotas, props.jeton, ["quotas", "poste"]);
  const envoi = useEnvoi<{ message?: string }>();
  const vue = lecture.valeur;
  if (vue === null) {
    return lecture.erreur === null ? <EnChargement /> : <BlocErreur erreur={lecture.erreur} message={T.poste.indisponible} />;
  }
  const relever = async () => {
    const fait = await envoi.envoyer(() => releverMaintenant());
    if (fait) props.apres();
  };
  const message = envoi.etat.etat === "ok" ? envoi.etat.resultat?.message : null;
  return (
    <div className="acp-sections">
      {lecture.erreur !== null ? (
        <p className="acp-alerte-texte" role="status">
          {T.poste.actualisationImpossible}
        </p>
      ) : null}
      <p className="acp-discret">{T.poste.quotasIntro}</p>
      <div className="acp-actions">
        <Bouton libelle={T.poste.releverMaintenant} surClic={relever} desactive={envoi.etat.etat === "envoi"} />
      </div>
      <RetourEnvoi etat={envoi.etat} />
      {typeof message === "string" ? (
        <p className="acp-succes" role="status">
          <Donnee valeur={message} />
        </p>
      ) : null}
      <div className="acp-grille">
        <Voie voie="poste-codex" quotas={vue["poste-codex"]} />
        <Voie voie="poste-claude" quotas={vue["poste-claude"]} />
        <Carte titre={T.poste.hermesTitre} id="acp-quotas-hermes">
          <p>
            <Donnee valeur={vue.hermes?.libelle} />
          </p>
        </Carte>
      </div>
    </div>
  );
}
