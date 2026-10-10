// Blocs de l'exécutant (étape P6, cahier P6 § 4.4, § 9.3), tous lus dans le bloc « executant » de GET /v1/poste :
// isolement MESURÉ par la sonde de plateforme (« Inconnu » sans sonde), conditions d'usage décidées, dernière
// réclamation, carte en cours, voies fermées et cartes qui les attendent, branches prêtes avec la commande de
// récupération. Aucun bouton « Pousser » : aucun identifiant d'écriture en P6 (D82).
import { T } from "../chaines";
import { Carte, Donnee, Ligne } from "../commun";
import { h, useState, type Noeud } from "../react";
import { Bouton, Etiquette, Horodatage } from "../projets/briques";
import type { BranchePrete, CarteEnMain, IsolementLinux, VueExecutant } from "./types";

const X = T.poste.executant;

function OuiNon(props: { valeur: unknown }): Noeud {
  if (typeof props.valeur !== "boolean") return <Donnee valeur={null} />;
  return <span>{props.valeur ? T.commun.oui : T.commun.non}</span>;
}

/** Libellé du régime mesuré ; jamais deviné. */
export function libelleRegime(regime: unknown): string {
  if (regime === "A") return X.regimeA;
  if (regime === "B") return X.regimeB;
  return X.regimeInconnu;
}

function Ecriture(props: { valeur: unknown }): Noeud {
  if (typeof props.valeur !== "boolean") return <Donnee valeur={null} />;
  return (
    <Etiquette libelle={{ texte: props.valeur ? X.admise : X.refusee, famille: props.valeur ? "succes" : "echec" }} />
  );
}

function Isolement(props: { isolement: IsolementLinux | null | undefined }): Noeud {
  const i = props.isolement;
  if (!i) {
    return (
      <Carte titre={X.isolementTitre} id="acp-poste-isolement">
        <p className="acp-alerte-texte">{X.isolementInconnu}</p>
      </Carte>
    );
  }
  const ecriture = i.ecriture_admise ?? {};
  const reseau = i.reseau_coupe === true ? X.reseauCoupe : i.reseau_coupe === false ? X.reseauNonCoupe : null;
  // Un /proc neuf refusé laisse voir les processus du conteneur (cahier P6 § 4.2).
  const processus = typeof i.proc_neuf === "boolean" ? !i.proc_neuf : null;
  return (
    <Carte titre={X.isolementTitre} id="acp-poste-isolement">
      <dl className="acp-liste">
        <Ligne libelle={X.regime}>
          <Etiquette libelle={{ texte: libelleRegime(i.regime), famille: i.regime === "A" ? "succes" : "degrade" }}
                     brut={i.regime} />
        </Ligne>
        <Ligne libelle={X.sondeLe}>
          <Donnee valeur={i.sonde_le} mono />
        </Ligne>
        <Ligne libelle={T.poste.raison}>
          <Donnee valeur={i.raison} />
        </Ligne>
        <Ligne libelle={X.reseau}>
          <Donnee valeur={reseau} />
        </Ligne>
        <Ligne libelle={X.processus}>
          <OuiNon valeur={processus} />
        </Ligne>
        <Ligne libelle={X.identifiants}>
          {i.uid_separes === true ? <span>{X.identifiantsProuves}</span> : <span>{X.identifiantsNonProuves}</span>}
        </Ligne>
        <Ligne libelle={X.ecritureCodex}>
          <Ecriture valeur={ecriture.codex} />
        </Ligne>
        <Ligne libelle={X.ecritureClaude}>
          <Ecriture valeur={ecriture.claude} />
        </Ligne>
      </dl>
    </Carte>
  );
}

function Conditions(props: { executant: VueExecutant }): Noeud {
  const conditions = props.executant.conditions;
  const bornes = props.executant.bornes ?? {};
  return (
    <Carte titre={X.conditionsTitre} id="acp-poste-conditions">
      <p className="acp-discret">{X.conditionsAide}</p>
      {conditions === null || conditions === undefined ? (
        <p className="acp-discret">{X.conditionsNonPubliees}</p>
      ) : (
        <dl className="acp-liste">
          {(["codex", "claude"] as const).map((cle) => (
            <Ligne key={cle} libelle={cle === "codex" ? T.poste.codex : T.poste.claude}>
              {typeof conditions[cle] === "string" ? (
                <span>
                  <span className="acp-discret">{X.decideLe}</span> <Donnee valeur={conditions[cle]} mono />
                </span>
              ) : (
                <Etiquette libelle={{ texte: X.nonDecide, famille: "echec" }} />
              )}
            </Ligne>
          ))}
          <Ligne libelle={X.cartesParJour}>
            <Donnee valeur={bornes.cartes_par_jour ?? null} />
          </Ligne>
          <Ligne libelle={X.dureeMax}>
            <Donnee valeur={bornes.duree_max_carte_s ?? null} />
          </Ligne>
          <Ligne libelle={X.concurrence}>
            <Donnee valeur={bornes.concurrence ?? null} />
          </Ligne>
        </dl>
      )}
    </Carte>
  );
}

function CarteEnCours(props: { carte: CarteEnMain | null | undefined; executant: VueExecutant }): Noeud {
  const c = props.carte;
  const voies = Array.isArray(props.executant.voies_disponibles) ? props.executant.voies_disponibles : null;
  return (
    <Carte titre={X.carteTitre} id="acp-poste-carte-en-cours">
      <dl className="acp-liste">
        <Ligne libelle={X.peutExecuter}>
          <OuiNon valeur={props.executant.peut_executer} />
        </Ligne>
        <Ligne libelle={X.voiesAnnoncees}>
          {voies === null ? <Donnee valeur={null} /> : voies.length === 0 ? <span>{X.aucuneVoie}</span>
            : <Donnee valeur={voies.join(", ")} mono />}
        </Ligne>
        <Ligne libelle={X.espaceLibre}>
          <Donnee valeur={props.executant.espace_libre_mio ?? null} />
        </Ligne>
      </dl>
      {!c ? (
        <p className="acp-discret">{X.aucuneCarte}</p>
      ) : c.connue === false ? (
        <p className="acp-alerte-texte">{X.carteInconnue}</p>
      ) : (
        <dl className="acp-liste">
          <Ligne libelle={X.projet}>
            <Donnee valeur={c.projet_titre} />
          </Ligne>
          <Ligne libelle={X.carte}>
            <span>
              <Donnee valeur={c.titre} /> <span className="acp-discret"><Donnee valeur={c.carte} mono /></span>
            </span>
          </Ligne>
          <Ligne libelle={X.role}>
            <Donnee valeur={c.role} />
          </Ligne>
          <Ligne libelle={X.voie}>
            <Donnee valeur={c.voie} mono />
          </Ligne>
          <Ligne libelle={X.modeleDemande}>
            <Donnee valeur={c.modele_demande} mono />
          </Ligne>
          <Ligne libelle={X.modeleServi}>
            <Donnee valeur={c.modele_servi} mono />
          </Ligne>
          <Ligne libelle={X.statut}>
            <Donnee valeur={c.statut} mono />
          </Ligne>
          <Ligne libelle={X.tenueParExecutant}>
            <OuiNon valeur={c.a_nous} />
          </Ligne>
          <Ligne libelle={X.dernierBattement}>
            <Horodatage valeur={c.dernier_battement} relative />
          </Ligne>
        </dl>
      )}
    </Carte>
  );
}

function VoiesFermees(props: { executant: VueExecutant }): Noeud {
  const fermees = Object.entries(props.executant.voies_fermees ?? {});
  const attente = Array.isArray(props.executant.cartes_en_attente_de_voie) ? props.executant.cartes_en_attente_de_voie
    : [];
  return (
    <Carte titre={X.voiesFermeesTitre} id="acp-poste-voies-fermees">
      {fermees.length === 0 ? (
        <p className="acp-discret">{X.aucuneVoieFermee}</p>
      ) : (
        <ul className="acp-liste">
          {fermees.map(([voie, raison]) => (
            <li key={voie} className="acp-etat">
              <Donnee valeur={voie} mono /> <Donnee valeur={raison} />
            </li>
          ))}
        </ul>
      )}
      {attente.length > 0 ? (
        <div className="acp-groupe">
          <p className="acp-discret">{X.enAttenteDeVoie}</p>
          <ul className="acp-liste">
            {attente.map((a, rang) => (
              <li key={a.carte ?? String(rang)} className="acp-etat">
                <Donnee valeur={a.titre} /> <Donnee valeur={a.voie} mono />
                <span className="acp-discret">{X.depuis}</span> <Horodatage valeur={a.depuis} relative />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Carte>
  );
}

function Branche(props: { branche: BranchePrete }): Noeud {
  const b = props.branche;
  const [copie, fixerCopie] = useState<"ok" | "impossible" | null>(null);
  const copier = async () => {
    const presse = globalThis.navigator?.clipboard;
    if (!b.commande || !presse || typeof presse.writeText !== "function") {
      fixerCopie("impossible");
      return;
    }
    try {
      await presse.writeText(b.commande);
      fixerCopie("ok");
    } catch {
      fixerCopie("impossible");
    }
  };
  return (
    <li className="acp-entree">
      <dl className="acp-liste">
        <Ligne libelle={X.projet}>
          <Donnee valeur={b.projet_titre} />
        </Ligne>
        <Ligne libelle={X.branche}>
          <Donnee valeur={b.branche} mono />
        </Ligne>
        <Ligne libelle={X.tete}>
          <Donnee valeur={b.tete} mono />
        </Ligne>
        <Ligne libelle={X.termineLe}>
          <Horodatage valeur={b.termine_le} />
        </Ligne>
        <Ligne libelle={X.commande}>
          <Donnee valeur={b.commande} mono />
        </Ligne>
      </dl>
      <div className="acp-actions">
        <Bouton libelle={X.copier} surClic={copier} />
      </div>
      {copie === "ok" ? <p className="acp-succes" role="status">{X.copie}</p> : null}
      {copie === "impossible" ? <p className="acp-alerte-texte" role="status">{X.copieImpossible}</p> : null}
    </li>
  );
}

function BranchesPretes(props: { branches: BranchePrete[] }): Noeud {
  return (
    <Carte titre={X.branchesTitre} id="acp-poste-branches">
      <p className="acp-discret">{X.branchesAide}</p>
      {props.branches.length === 0 ? (
        <p className="acp-discret">{X.aucuneBranche}</p>
      ) : (
        <ul className="acp-entrees acp-entrees--une">
          {props.branches.map((b, rang) => (
            <Branche key={`${b.branche ?? rang}`} branche={b} />
          ))}
        </ul>
      )}
    </Carte>
  );
}

/** Blocs de l'exécutant ; rien si le greffon ne connaît aucun poste. */
export function Executant(props: { executant: VueExecutant | undefined }): Noeud {
  const e = props.executant;
  if (!e || e.connu !== true) return null;
  const linux = e.plateforme === "linux";
  const branches = Array.isArray(e.branches_pretes) ? e.branches_pretes : [];
  return (
    <div className="acp-grille">
      {linux ? <Isolement isolement={e.isolement} /> : null}
      <Conditions executant={e} />
      <CarteEnCours carte={e.carte_en_cours} executant={e} />
      <VoiesFermees executant={e} />
      <BranchesPretes branches={branches} />
      {typeof e.revues === "number" && e.revues > 0 ? (
        <Carte titre={X.revuesEnAttente} id="acp-poste-revues">
          <p>
            <Donnee valeur={e.revues} />
          </p>
        </Carte>
      ) : null}
    </div>
  );
}
