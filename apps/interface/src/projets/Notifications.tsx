// Carte « Notifications » : canal vu par l'émetteur de la passerelle (bloc notifications de
// GET /v1/projets) et envoi d'une notification de test (POST /v1/notifications/test, 202). Le bouton
// n'est actif que si un canal est configuré : sinon il le dit, et rien ne fait semblant d'envoyer.
import { T } from "../chaines";
import { Carte, Donnee, Ligne } from "../commun";
import { h, type Noeud } from "../react";
import { chaine } from "../types";
import { notificationDeTest } from "./api";
import { Bouton, Etiquette, RetourEnvoi } from "./briques";
import { useEnvoi } from "./envoi";
import { libelleCanal } from "./libelles";
import type { EtatNotifications } from "./types";

export function Notifications(props: { etat: EtatNotifications | null | undefined }): Noeud {
  const etat = props.etat ?? null;
  const envoi = useEnvoi<{ message?: unknown }>();
  const configure = etat?.configure === true;
  const canal = etat?.connu ? etat.canal : null;
  const libelle = libelleCanal(canal);
  const message = envoi.etat.etat === "ok" ? chaine(envoi.etat.resultat?.message) : null;
  return (
    <Carte titre={T.projets.notificationsTitre} id="acp-projets-notifications">
      <dl className="acp-liste">
        <Ligne libelle={T.projets.canal}>
          {libelle ? <span>{libelle}</span> : <Donnee valeur={chaine(canal)} mono />}
        </Ligne>
        <Ligne libelle={T.projets.etatNotifications}>
          <Etiquette
            libelle={
              etat?.connu !== true
                ? null
                : configure
                  ? { texte: T.projets.notificationsActives, famille: "succes" }
                  : { texte: T.projets.notificationsInactives, famille: "neutre" }
            }
          />
        </Ligne>
      </dl>
      {configure ? null : (
        <p className="acp-discret" id="acp-notifications-note">
          {T.projets.notificationsNonConfigurees}
        </p>
      )}
      <div className="acp-actions">
        <Bouton
          libelle={T.projets.envoyerTest}
          desactive={!configure || envoi.etat.etat === "envoi"}
          decritPar={configure ? undefined : "acp-notifications-note"}
          surClic={() => void envoi.envoyer(notificationDeTest)}
        />
      </div>
      <RetourEnvoi etat={envoi.etat} />
      {message ? (
        <p className="acp-succes" role="status">
          <Donnee valeur={message} />
        </p>
      ) : null}
    </Carte>
  );
}
