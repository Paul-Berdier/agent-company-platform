// Cartes « Exécutant » et « Quotas » de l'Accueil (cahier P7 § 8.3, blocs 3 et 4) : état RÉEL de l'exécutant (nom de
// la machine enregistrée, jamais un libellé écrit en dur), carte en cours, voies fermées et leur raison ; quotas par
// voie avec la source et la date du relevé. Rien n'est estimé : une valeur absente reste « Inconnu ».
import { T } from "../chaines";
import { Carte, Donnee, Ligne, Lien } from "../commun";
import { h, type Noeud } from "../react";
import { chaine } from "../types";
import { Etiquette, Horodatage } from "../projets/briques";
import { libelleStatut } from "../projets/libelles";
import { libelleEtatDuPoste, libelleEtatQuotas, libelleVoie } from "../poste/libelles";
import type { ExecutantAccueil, QuotaAccueil } from "./accueil-api";

function Illisible(props: { raison: string | null }): Noeud {
  return (
    <p className="acp-alerte-texte">
      <span>{T.accueil.blocIllisible}</span> <Donnee valeur={props.raison} />
    </p>
  );
}

export function CarteExecutant(props: { executant: ExecutantAccueil | null | undefined; illisible: string | null }):
  Noeud {
  const e = props.executant ?? null;
  const fermees = e?.voies_fermees && typeof e.voies_fermees === "object" ? Object.entries(e.voies_fermees) : [];
  const enCours = e?.carte_en_cours ?? null;
  return (
    <Carte titre={T.accueil.executantTitre} id="acp-accueil-executant">
      {e === null ? (
        <Illisible raison={props.illisible} />
      ) : (
        <div className="acp-sections">
          <dl className="acp-liste">
            <Ligne libelle={T.accueil.etat}>
              <Etiquette libelle={libelleEtatDuPoste(e.etat)} brut={e.etat} />
            </Ligne>
            <Ligne libelle={T.accueil.machine}>
              <Donnee valeur={chaine(e.nom)} />
            </Ligne>
            <Ligne libelle={T.accueil.plateforme}>
              <Donnee valeur={chaine(e.plateforme)} mono />
            </Ligne>
            <Ligne libelle={T.accueil.derniereVue}>
              <Horodatage valeur={e.derniere_vue} relative />
            </Ligne>
            <Ligne libelle={T.accueil.carteEnCours}>
              {enCours ? (
                <span>
                  <Donnee valeur={chaine(enCours.titre)} />{" "}
                  <span className="acp-discret">
                    <Donnee valeur={chaine(enCours.projet_titre)} />
                  </span>{" "}
                  <Etiquette libelle={libelleStatut(enCours.statut)} brut={enCours.statut} />
                </span>
              ) : (
                <span>{T.accueil.aucuneCarteEnCours}</span>
              )}
            </Ligne>
          </dl>
          {chaine(e.message) ? (
            <p className="acp-discret">
              <Donnee valeur={chaine(e.message)} />
            </p>
          ) : null}
          {fermees.length > 0 ? (
            <div>
              <p className="acp-discret">{T.accueil.voiesFermees}</p>
              <ul className="acp-noms">
                {fermees.map(([voie, raison]) => (
                  <li key={voie}>
                    {libelleVoie(voie) ? <span>{libelleVoie(voie)}</span> : <Donnee valeur={voie} mono />}{" "}
                    <span className="acp-discret">
                      <Donnee valeur={typeof raison === "string" ? raison : null} />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
      <p>
        <Lien vers="/poste">{T.accueil.ouvrirPoste}</Lien>
      </p>
    </Carte>
  );
}

const VOIES_QUOTAS = ["poste-codex", "poste-claude"] as const;

function pourcentage(valeur: unknown): string | null {
  return typeof valeur === "number" && Number.isFinite(valeur) && valeur >= 0 && valeur <= 100 ? `${valeur} %` : null;
}

export function CarteQuotas(props: { quotas: Record<string, QuotaAccueil> | null | undefined; illisible: string | null }):
  Noeud {
  const quotas = props.quotas ?? null;
  return (
    <Carte titre={T.accueil.quotasTitre} id="acp-accueil-quotas">
      {quotas === null ? (
        <Illisible raison={props.illisible} />
      ) : (
        <div className="acp-sections">
          {VOIES_QUOTAS.map((voie) => {
            const q = quotas[voie] ?? {};
            return (
              <div key={voie} className="acp-groupe">
                <h3 className="acp-sous-titre">{libelleVoie(voie)}</h3>
                <dl className="acp-liste">
                  <Ligne libelle={T.accueil.etat}>
                    <Etiquette libelle={libelleEtatQuotas(q.etat)} brut={q.etat} />
                  </Ligne>
                  <Ligne libelle={T.accueil.utilise}>
                    <Donnee valeur={pourcentage(q.resume?.pourcentage_utilise)} />
                  </Ligne>
                  <Ligne libelle={T.accueil.remiseAZero}>
                    <Horodatage valeur={q.resume?.remise_a_zero} />
                  </Ligne>
                  <Ligne libelle={T.accueil.source}>
                    <Donnee valeur={chaine(q.source_libelle)} />
                  </Ligne>
                  <Ligne libelle={T.accueil.releveLe}>
                    <Horodatage valeur={q.releve_le} />
                  </Ligne>
                </dl>
              </div>
            );
          })}
          <div className="acp-groupe">
            <h3 className="acp-sous-titre">{T.accueil.quotasHermes}</h3>
            <p>
              <Donnee valeur={chaine(quotas.hermes?.libelle)} />
            </p>
          </div>
        </div>
      )}
      <p>
        <Lien vers="/poste?vue=quotas">{T.accueil.ouvrirQuotas}</Lien>
      </p>
    </Carte>
  );
}
