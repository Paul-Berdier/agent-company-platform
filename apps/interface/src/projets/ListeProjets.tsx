// Vue « liste » : une carte par projet (état, avancement, poste, questions, dernière note), puis le
// poste Windows, les notifications et la commande de pause générale.
import { T } from "../chaines";
import { Carte, Donnee, Ligne } from "../commun";
import { nombre } from "../format";
import { h, type Noeud } from "../react";
import { chaine } from "../types";
import { CommandePause } from "./BandeauPause";
import { EtatDuPoste, Etiquette, Horodatage, LienVue, type Naviguer } from "./briques";
import { libelleEtatProjet } from "./libelles";
import { Notifications } from "./Notifications";
import type { EtatPoste, ListeProjets as DonneesListe, ResumeProjet } from "./types";

const entier = (v: unknown): number | null => (typeof v === "number" && Number.isInteger(v) && v >= 0 ? v : null);

/** « 4 sur 9 » et une barre (décorative : le texte porte l'information). */
export function Avancement(props: { faites: unknown; total: unknown }): Noeud {
  const faites = entier(props.faites);
  const total = entier(props.total);
  const part = faites !== null && total !== null && total > 0 ? Math.min(100, Math.round((100 * faites) / total)) : 0;
  return (
    <span className="acp-avancement">
      <span>
        <Donnee valeur={nombre(faites)} /> <span className="acp-discret">{T.projets.sur}</span>{" "}
        <Donnee valeur={nombre(total)} />
      </span>
      <span className="acp-barre" aria-hidden="true">
        <span className="acp-barre__plein" style={{ width: `${part}%` }} />
      </span>
    </span>
  );
}

function DerniereNote(props: { projet: ResumeProjet }): Noeud {
  const note = chaine(props.projet.derniere_note);
  if (note) return <Donnee valeur={note} />;
  // Compteurs lisibles et aucune carte finie : c'est un fait, pas une donnée manquante.
  if (entier(props.projet.compteurs?.faites) === 0) return <span className="acp-discret">{T.projets.aucuneNote}</span>;
  return <Donnee valeur={null} />;
}

function CarteDeProjet(props: { projet: ResumeProjet; poste: EtatPoste | undefined; naviguer: Naviguer }): Noeud {
  const { projet } = props;
  const id = chaine(projet.id);
  const compteurs = projet.compteurs ?? {};
  const questions = entier(projet.questions_ouvertes);
  return (
    <li className="acp-entree acp-projet">
      <h3 className="acp-entree__nom">
        {id ? (
          <LienVue vue={{ genre: "detail", id }} naviguer={props.naviguer} className="acp-lien acp-lien--titre">
            <Donnee valeur={chaine(projet.titre)} />
          </LienVue>
        ) : (
          <Donnee valeur={chaine(projet.titre)} />
        )}
      </h3>
      <p className="acp-etat">
        <Etiquette libelle={libelleEtatProjet(projet.etat, projet.etat_derive)} brut={projet.etat} />
        {questions !== null && questions > 0 ? (
          <span className="acp-pastille acp-pastille--degrade">
            <span>{T.projets.questionsEnAttente}</span> <Donnee valeur={questions} />
          </span>
        ) : null}
      </p>
      <dl className="acp-liste">
        <Ligne libelle={T.projets.cartesFaites}>
          <Avancement faites={compteurs.faites} total={compteurs.total} />
        </Ligne>
        {entier(compteurs.en_attente_du_poste) ? (
          <Ligne libelle={T.projets.enAttenteDuPoste}>
            <Donnee valeur={nombre(compteurs.en_attente_du_poste)} />
          </Ligne>
        ) : null}
        {entier(compteurs.bloquees) ? (
          <Ligne libelle={T.projets.bloquees}>
            <Donnee valeur={nombre(compteurs.bloquees)} />
          </Ligne>
        ) : null}
        {entier(compteurs.triage) ? (
          <Ligne libelle={T.projets.enTriage}>
            <Donnee valeur={nombre(compteurs.triage)} />
          </Ligne>
        ) : null}
        <Ligne libelle={T.projets.poste}>
          <EtatDuPoste poste={props.poste} />
        </Ligne>
        <Ligne libelle={T.projets.derniereNote}>
          <DerniereNote projet={projet} />
        </Ligne>
        <Ligne libelle={T.projets.creeLe}>
          <Horodatage valeur={projet.cree_le} relative />
        </Ligne>
      </dl>
    </li>
  );
}

function CartePoste(props: { poste: EtatPoste | undefined }): Noeud {
  const poste = props.poste;
  return (
    <Carte titre={T.projets.posteTitre} id="acp-projets-poste">
      <dl className="acp-liste">
        <Ligne libelle={T.projets.etat}>
          <EtatDuPoste poste={poste} />
        </Ligne>
        {chaine(poste?.machine) ? (
          <Ligne libelle={T.projets.machine}>
            <Donnee valeur={chaine(poste?.machine)} mono />
          </Ligne>
        ) : null}
        {poste?.derniere_vue ? (
          <Ligne libelle={T.projets.derniereVue}>
            <Horodatage valeur={poste.derniere_vue} />
          </Ligne>
        ) : null}
        <Ligne libelle={T.projets.cartesEnAttente}>
          <Donnee valeur={nombre(poste?.cartes_en_attente)} />
        </Ligne>
      </dl>
      {chaine(poste?.message) ? (
        <p className="acp-discret">
          <Donnee valeur={chaine(poste?.message)} />
        </p>
      ) : null}
    </Carte>
  );
}

export function ListeProjets(props: { donnees: DonneesListe; naviguer: Naviguer; apres: () => void }): Noeud {
  const { donnees } = props;
  const projets = Array.isArray(donnees.projets) ? donnees.projets : [];
  return (
    <div className="acp-sections">
      <Carte titre={T.projets.vosProjets} id="acp-projets-liste">
        <div className="acp-actions">
          <LienVue vue={{ genre: "nouveau" }} naviguer={props.naviguer} className="acp-bouton acp-bouton--principal">
            {T.projets.nouveauProjet}
          </LienVue>
        </div>
        {projets.length === 0 ? (
          <p className="acp-discret">{T.projets.aucunProjet}</p>
        ) : (
          <ul className="acp-entrees">
            {projets.map((p, rang) => (
              <CarteDeProjet key={chaine(p.id) ?? String(rang)} projet={p} poste={donnees.poste} naviguer={props.naviguer} />
            ))}
          </ul>
        )}
      </Carte>
      <div className="acp-grille">
        <CartePoste poste={donnees.poste} />
        <Notifications etat={donnees.notifications} />
        {donnees.pause_generale ? null : <CommandePause apres={props.apres} />}
      </div>
    </div>
  );
}
