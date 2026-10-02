// Vue « Poste » : bandeau d'état (Non configuré / À confirmer + empreinte / En ligne / Hors ligne depuis / En
// redéploiement / Révoqué), enrôlement, confirmation de l'empreinte, révocation, « Relever maintenant », puis (étape P6)
// les blocs de l'exécutant (isolement, conditions d'usage, carte en cours, voies fermées, branches prêtes) et ce que dit
// le dernier inventaire (compte, versions, bac à sable Codex, connexions, dépôts, alertes) et les ordres en attente.
// Tout vient de GET /v1/poste ; rien n'est deviné.
import { T } from "../chaines";
import { BlocErreur, Carte, Donnee, EnChargement, Ligne } from "../commun";
import { h, useState, type Noeud } from "../react";
import { Bouton, Etiquette, Horodatage, RetourEnvoi } from "../projets/briques";
import { useEnvoi } from "../projets/envoi";
import { useDonnees } from "../donnees";
import { confirmer, lirePostePage, releverMaintenant, revoquer } from "./api";
import { Enrolement } from "./Enrolement";
import { Executant } from "./Executant";
import {
  libelleConnexionClaude,
  libelleConnexionCodex,
  libelleEtatDuPoste,
  libelleGenreOrdre,
} from "./libelles";
import type { ContenuInventaire, MachineVue, ReponsePostePage, ResultatReleve } from "./types";

function OuiNon(props: { valeur: unknown }): Noeud {
  if (typeof props.valeur !== "boolean") return <Donnee valeur={null} />;
  return <span>{props.valeur ? T.commun.oui : T.commun.non}</span>;
}

function Bandeau(props: { donnees: ReponsePostePage }): Noeud {
  const etat = props.donnees.poste;
  const machine = props.donnees.machine?.machine;
  // Étape P6 : « Exécutant Railway » quand l'inventaire dit hote = railway, sinon le titre du poste.
  const executant = props.donnees.executant?.hote === "railway";
  return (
    <Carte titre={executant ? T.poste.etatTitreExecutant : T.poste.etatTitre} id="acp-poste-etat">
      <p className="acp-etat">
        <Etiquette libelle={libelleEtatDuPoste(etat?.etat)} brut={etat?.etat} />
        {etat?.etat === "a_confirmer" ? <Donnee valeur={machine?.empreinte} mono /> : null}
        {etat?.etat === "en_ligne" ? (
          <span>
            <span className="acp-discret">{T.poste.vu}</span> <Horodatage valeur={etat.derniere_vue} relative />
          </span>
        ) : null}
        {(etat?.etat === "hors_ligne" || etat?.etat === "redeploiement") && etat.hors_ligne_depuis ? (
          <span>
            <span className="acp-discret">{T.poste.depuis}</span> <Horodatage valeur={etat.hors_ligne_depuis} />
          </span>
        ) : null}
        {etat?.etat === "revoque" ? (
          <span>
            <span className="acp-discret">{T.poste.revoqueLe}</span> <Horodatage valeur={machine?.revoque_le} />
          </span>
        ) : null}
      </p>
      {etat?.message ? (
        <p>
          <Donnee valeur={etat.message} />
        </p>
      ) : null}
      {machine && machine.politique_valide === false ? (
        <p className="acp-alerte-texte">{T.poste.politiqueInvalide}</p>
      ) : null}
      {etat?.pause_reclamations ? <p className="acp-alerte-texte">{T.poste.pauseReclamations}</p> : null}
      <dl className="acp-liste">
        <Ligne libelle={T.poste.cartesEnAttente}>
          <Donnee valeur={typeof etat?.cartes_en_attente === "number" ? etat.cartes_en_attente : null} />
        </Ligne>
      </dl>
    </Carte>
  );
}

function Confirmation(props: { machine: MachineVue; apres: () => void }): Noeud {
  const [saisie, fixerSaisie] = useState("");
  const envoi = useEnvoi();
  const envoyer = async (evenement: { preventDefault: () => void }) => {
    evenement.preventDefault();
    const fait = await envoi.envoyer(() => confirmer(String(props.machine.id ?? ""), saisie));
    if (fait) props.apres();
  };
  return (
    <Carte titre={T.poste.confirmerTitre} id="acp-poste-confirmation">
      <dl className="acp-liste">
        <Ligne libelle={T.poste.empreinteAnnoncee}>
          <Donnee valeur={props.machine.empreinte} mono />
        </Ligne>
        <Ligne libelle={T.poste.nom}>
          <Donnee valeur={props.machine.nom} />
        </Ligne>
      </dl>
      <p className="acp-discret" id="acp-poste-empreinte-aide">
        {T.poste.empreinteAide}
      </p>
      <form className="acp-formulaire" onSubmit={envoyer}>
        <div className="acp-champ">
          <label htmlFor="acp-poste-empreinte">{T.poste.champEmpreinte}</label>
          <input id="acp-poste-empreinte" value={saisie} autoComplete="off" spellCheck={false}
                 aria-describedby="acp-poste-empreinte-aide" onChange={(e) => fixerSaisie(e.currentTarget.value)} />
        </div>
        <div className="acp-actions">
          <Bouton type="submit" libelle={T.poste.confirmer} principal desactive={envoi.etat.etat === "envoi" || !saisie.trim()} />
        </div>
      </form>
      <RetourEnvoi etat={envoi.etat} reussite={T.poste.confirme} />
    </Carte>
  );
}

function Revocation(props: { machine: MachineVue; apres: () => void }): Noeud {
  const [ouvert, fixerOuvert] = useState(false);
  const [motif, fixerMotif] = useState("");
  const envoi = useEnvoi();
  const envoyer = async () => {
    const fait = await envoi.envoyer(() => revoquer(String(props.machine.id ?? ""), motif));
    if (fait) {
      fixerOuvert(false);
      props.apres();
    }
  };
  return (
    <Carte titre={T.poste.revoquerTitre} id="acp-poste-revocation">
      <p className="acp-discret">{T.poste.revoquerAide}</p>
      {!ouvert ? (
        <div className="acp-actions">
          <Bouton libelle={T.poste.revoquer} danger surClic={() => fixerOuvert(true)} />
        </div>
      ) : (
        <div className="acp-confirmation" role="group" aria-labelledby="acp-poste-revoquer-question">
          <p id="acp-poste-revoquer-question">{T.poste.revoquerQuestion}</p>
          <div className="acp-champ">
            <label htmlFor="acp-poste-motif">{T.poste.champMotif}</label>
            <input id="acp-poste-motif" value={motif} maxLength={200} onChange={(e) => fixerMotif(e.currentTarget.value)} />
          </div>
          <div className="acp-actions">
            <Bouton libelle={T.poste.confirmerRevocation} danger surClic={envoyer}
                    desactive={envoi.etat.etat === "envoi" || !motif.trim()} />
            <Bouton libelle={T.poste.annuler} surClic={() => fixerOuvert(false)} />
          </div>
        </div>
      )}
      <RetourEnvoi etat={envoi.etat} reussite={T.poste.revoque} />
    </Carte>
  );
}

function Releve(props: { apres: () => void }): Noeud {
  const envoi = useEnvoi<ResultatReleve>();
  const envoyer = async () => {
    const fait = await envoi.envoyer(() => releverMaintenant());
    if (fait) props.apres();
  };
  const message = envoi.etat.etat === "ok" ? envoi.etat.resultat?.message : null;
  return (
    <Carte titre={T.poste.releverTitre} id="acp-poste-releve">
      <p className="acp-discret">{T.poste.releverAide}</p>
      <div className="acp-actions">
        <Bouton libelle={T.poste.releverMaintenant} surClic={envoyer} desactive={envoi.etat.etat === "envoi"} />
      </div>
      <RetourEnvoi etat={envoi.etat} />
      {typeof message === "string" ? (
        <p className="acp-succes" role="status">
          <Donnee valeur={message} />
        </p>
      ) : null}
    </Carte>
  );
}

function Machine(props: { machine: MachineVue }): Noeud {
  const m = props.machine;
  return (
    <Carte titre={T.poste.machineTitre} id="acp-poste-machine">
      <dl className="acp-liste">
        <Ligne libelle={T.poste.nom}>
          <Donnee valeur={m.nom} />
        </Ligne>
        <Ligne libelle={T.poste.empreinte}>
          <Donnee valeur={m.empreinte} mono />
        </Ligne>
        <Ligne libelle={T.poste.versionPoste}>
          <Donnee valeur={m.version_poste} mono />
        </Ligne>
        <Ligne libelle={T.poste.protocole}>
          <Donnee valeur={m.protocole} mono />
        </Ligne>
        <Ligne libelle={T.poste.enroleLe}>
          <Horodatage valeur={m.cree_le} />
        </Ligne>
        <Ligne libelle={T.poste.confirmeLe}>
          <Horodatage valeur={m.confirme_le} />
        </Ligne>
        <Ligne libelle={T.poste.derniereRequete}>
          <Horodatage valeur={m.derniere_requete} relative />
        </Ligne>
      </dl>
    </Carte>
  );
}

function Inventaire(props: { donnees: ReponsePostePage }): Noeud {
  const inventaire = props.donnees.inventaire;
  const c: ContenuInventaire = inventaire?.contenu ?? {};
  if (!inventaire) {
    return (
      <Carte titre={T.poste.inventaireTitre} id="acp-poste-inventaire">
        <p className="acp-discret">{T.poste.aucunInventaire}</p>
      </Carte>
    );
  }
  const bac = c.bac_a_sable_codex ?? {};
  const versions = c.versions ?? {};
  const depots = Array.isArray(c.depots) ? c.depots : [];
  return (
    <div className="acp-grille">
      <Carte titre={T.poste.inventaireTitre} id="acp-poste-inventaire">
        <dl className="acp-liste">
          <Ligne libelle={T.poste.recuLe}>
            <Horodatage valeur={inventaire.recu_le} />
          </Ligne>
          <Ligne libelle={T.poste.releveLe}>
            <Horodatage valeur={inventaire.releve_le} />
          </Ligne>
          <Ligne libelle={T.poste.versionPoste}>
            <Donnee valeur={c.version_poste} mono />
          </Ligne>
        </dl>
      </Carte>
      <Carte titre={T.poste.compteTitre} id="acp-poste-compte">
        <dl className="acp-liste">
          <Ligne libelle={T.poste.compte}>
            {c.poste?.compte === "dedie" ? <span>{T.poste.compteDedie}</span>
              : c.poste?.compte === "proprietaire" ? <span>{T.poste.compteProprietaire}</span>
              : c.poste?.compte === "uid_dedie" ? <span>{T.poste.compteUidDedie}</span>
              : <Donnee valeur={c.poste?.compte} />}
          </Ligne>
          {c.poste?.plateforme === "linux" ? (
            <Ligne libelle={T.poste.executant.noyau}>
              <Donnee valeur={c.poste?.noyau} mono />
            </Ligne>
          ) : (
            <Ligne libelle={T.poste.windows}>
              <Donnee valeur={c.poste?.windows} mono />
            </Ligne>
          )}
          <Ligne libelle={T.poste.python}>
            <Donnee valeur={c.poste?.python} mono />
          </Ligne>
          <Ligne libelle={T.poste.empreintePolitique}>
            <Donnee valeur={c.poste?.politique_empreinte} mono />
          </Ligne>
        </dl>
      </Carte>
      <Carte titre={T.poste.versionsTitre} id="acp-poste-versions">
        <dl className="acp-liste">
          {(["codex", "claude"] as const).map((cle) => (
            <Ligne key={cle} libelle={cle === "codex" ? T.poste.codex : T.poste.claude}>
              <span className="acp-etat">
                <span className="acp-discret">{T.poste.lue}</span> <Donnee valeur={versions[cle]?.lue} mono />
                <span className="acp-discret">{T.poste.testee}</span> <Donnee valeur={versions[cle]?.testee} mono />
                <span className="acp-discret">{T.poste.conformite}</span> <OuiNon valeur={versions[cle]?.conforme} />
              </span>
            </Ligne>
          ))}
        </dl>
      </Carte>
      {c.poste?.plateforme === "linux" ? null : <Carte titre={T.poste.bacTitre} id="acp-poste-bac">
        <dl className="acp-liste">
          <Ligne libelle={T.poste.readiness}>
            <Donnee valeur={bac.readiness} mono />
          </Ligne>
          <Ligne libelle={T.poste.modeLu}>
            <Donnee valeur={bac.mode_lu} mono />
          </Ligne>
          <Ligne libelle={T.poste.origineMode}>
            <Donnee valeur={bac.origine_mode} mono />
          </Ligne>
          <Ligne libelle={T.poste.palierLu}>
            <Donnee valeur={bac.palier_lu} mono />
          </Ligne>
          <Ligne libelle={T.poste.stockage}>
            <Donnee valeur={bac.stockage_identifiants_lu} mono />
          </Ligne>
          <Ligne libelle={T.poste.ecritureAdmise}>
            <OuiNon valeur={bac.ecriture_admise} />
          </Ligne>
          {bac.raison ? (
            <Ligne libelle={T.poste.raison}>
              <Donnee valeur={bac.raison} />
            </Ligne>
          ) : null}
        </dl>
      </Carte>}
      <Carte titre={T.poste.connexionsTitre} id="acp-poste-connexions">
        <dl className="acp-liste">
          <Ligne libelle={T.poste.codex}>
            <Etiquette libelle={libelleConnexionCodex(c.connexions?.codex)} brut={c.connexions?.codex} />
          </Ligne>
          <Ligne libelle={T.poste.offre}>
            <Donnee valeur={c.connexions?.plan_codex} mono />
          </Ligne>
          <Ligne libelle={T.poste.claude}>
            <Etiquette libelle={libelleConnexionClaude(c.connexions?.claude)} brut={c.connexions?.claude} />
          </Ligne>
        </dl>
      </Carte>
      <Carte titre={T.poste.depotsTitre} id="acp-poste-depots">
        {depots.length === 0 ? (
          <p className="acp-discret">{T.poste.aucunDepot}</p>
        ) : (
          <ul className="acp-liste">
            {depots.map((d, i) => (
              <li key={`${d.alias ?? i}`}>
                <Donnee valeur={d.alias} mono />
              </li>
            ))}
          </ul>
        )}
      </Carte>
    </div>
  );
}

export function EtatPoste(props: { jeton: number; apres: () => void }): Noeud {
  const lecture = useDonnees(lirePostePage, props.jeton, ["poste", "projets", "pause", "quotas"]);
  const donnees = lecture.valeur;
  if (donnees === null) {
    return lecture.erreur === null ? <EnChargement /> : <BlocErreur erreur={lecture.erreur} message={T.poste.indisponible} />;
  }
  const etat = donnees.poste?.etat;
  const machine = donnees.machine?.machine ?? null;
  const alertes = Array.isArray(donnees.alertes) ? donnees.alertes : [];
  const ordres = Array.isArray(donnees.ordres) ? donnees.ordres : [];
  return (
    <div className="acp-sections">
      {lecture.erreur !== null ? (
        <p className="acp-alerte-texte" role="status">
          {T.poste.actualisationImpossible}
        </p>
      ) : null}
      <Bandeau donnees={donnees} />
      {etat === "non_configure" || etat === "revoque" || etat === "a_confirmer" ? (
        <Carte titre={T.poste.enrolerTitre} id="acp-poste-enroler">
          <Enrolement apres={props.apres} />
        </Carte>
      ) : null}
      {etat === "a_confirmer" && machine ? <Confirmation machine={machine} apres={props.apres} /> : null}
      {machine && machine.etat !== "revoque" ? <Machine machine={machine} /> : null}
      {machine && machine.etat === "actif" ? <Releve apres={props.apres} /> : null}
      <Executant executant={donnees.executant} />
      {alertes.length > 0 ? (
        <Carte titre={T.poste.alertesTitre} id="acp-poste-alertes">
          <ul className="acp-liste">
            {alertes.map((a, i) => (
              <li key={i}>
                <Donnee valeur={a} />
              </li>
            ))}
          </ul>
        </Carte>
      ) : null}
      {machine && machine.etat === "actif" ? (
        <Carte titre={T.poste.ordresTitre} id="acp-poste-ordres">
          {ordres.length === 0 ? (
            <p className="acp-discret">{T.poste.aucunOrdre}</p>
          ) : (
            <ul className="acp-liste">
              {ordres.map((o) => (
                <li key={o.id} className="acp-etat">
                  <Donnee valeur={libelleGenreOrdre(o.genre) ?? o.genre} />
                  <Horodatage valeur={o.cree_le} relative />
                  <span className="acp-discret">{o.livre ? T.poste.livre : T.poste.nonLivre}</span>
                </li>
              ))}
            </ul>
          )}
        </Carte>
      ) : null}
      <Inventaire donnees={donnees} />
      {machine && machine.etat !== "revoque" ? <Revocation machine={machine} apres={props.apres} /> : null}
    </div>
  );
}
