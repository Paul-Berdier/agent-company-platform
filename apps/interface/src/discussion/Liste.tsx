// Liste des discussions (cahier P7 § 9.2) : les vingt dernières sessions « tui » du tableau de bord (route REST
// native /api/sessions, celles qu'ouvrent /api/ws et /chat ; jamais les sessions des workers kanban, du cron ni d'une
// messagerie, dont la reprise changerait de plateforme), la plus récente d'abord, et « Nouvelle discussion ».
// Une session dont une question attend une réponse (session.active_list, jsonrpc/discussions.ts) est marquée.
import type * as ReactTypes from "react";
import { T } from "../chaines";
import { lireJSON } from "../api";
import { BlocErreur, Carte, Donnee, EnChargement, Ligne } from "../commun";
import { useDonnees } from "../donnees";
import { lireDiscussionsEnAttente } from "../jsonrpc/discussions";
import { Etiquette, Horodatage } from "../projets/briques";
import { h, type Noeud } from "../react";
import { chaine, type PageSessions } from "../types";
import { adresseDeVue, type NaviguerDiscussion, type VueDiscussion } from "./vue";

export const ROUTE_DISCUSSIONS = "/api/sessions?limit=20&offset=0&order=recent&source=tui";

export const lireDiscussions = (): Promise<PageSessions> => lireJSON<PageSessions>(ROUTE_DISCUSSIONS);

/** Vrai lien (nouvel onglet possible) ; un clic simple change de vue sans recharger la page. */
export function LienDiscussion(props: { vue: VueDiscussion; naviguer: NaviguerDiscussion; className?: string;
                                        children?: Noeud }): Noeud {
  const surClic = (evenement: ReactTypes.MouseEvent<HTMLAnchorElement>) => {
    if (evenement.defaultPrevented || evenement.button !== 0) return;
    if (evenement.metaKey || evenement.ctrlKey || evenement.shiftKey || evenement.altKey) return;
    evenement.preventDefault();
    props.naviguer(props.vue);
  };
  return (
    <a className={props.className ?? "acp-lien"} href={adresseDeVue(props.vue)} onClick={surClic}>
      {props.children}
    </a>
  );
}

export function Liste(props: { naviguer: NaviguerDiscussion }): Noeud {
  const lecture = useDonnees(lireDiscussions, 0, ["discussions"]);
  const attente = useDonnees(lireDiscussionsEnAttente, 0, ["discussions"]);
  const enAttente = new Set(attente.valeur?.connu ? attente.valeur.sessions.map((s) => s.cle) : []);
  const sessions = (lecture.valeur?.sessions ?? []).filter((s) => chaine(s.id) !== null);
  let contenu: Noeud;
  if (lecture.valeur === null) {
    contenu = lecture.erreur ? <BlocErreur erreur={lecture.erreur} message={T.discussion.listeIndisponible} /> : <EnChargement />;
  } else if (sessions.length === 0) {
    contenu = <p className="acp-discret">{T.discussion.aucune}</p>;
  } else {
    contenu = (
      <ul className="acp-entrees acp-entrees--une">
        {sessions.map((s) => {
          const cle = s.id as string;
          return (
            <li key={cle} className="acp-entree">
              <h3 className="acp-entree__nom">
                {chaine(s.title) ? <Donnee valeur={s.title} /> : <span>{T.discussion.sansTitre}</span>}
              </h3>
              <dl className="acp-liste">
                {enAttente.has(cle) ? (
                  <Ligne libelle={T.projets.discussionEtat}>
                    <Etiquette libelle={{ texte: T.discussion.enAttente, famille: "degrade" }} />
                  </Ligne>
                ) : null}
                <Ligne libelle={T.discussion.activite}>
                  <Horodatage valeur={s.last_active ?? s.started_at} relative />
                </Ligne>
                <Ligne libelle={T.discussion.messages}>
                  <Donnee valeur={typeof s.message_count === "number" ? s.message_count : null} />
                </Ligne>
              </dl>
              <div className="acp-actions">
                <LienDiscussion vue={{ genre: "fil", cle }} naviguer={props.naviguer} className="acp-bouton">
                  {T.discussion.ouvrir}
                </LienDiscussion>
              </div>
            </li>
          );
        })}
      </ul>
    );
  }
  return (
    <div className="acp-sections">
      <div className="acp-actions">
        <LienDiscussion vue={{ genre: "fil", cle: null }} naviguer={props.naviguer}
                        className="acp-bouton acp-bouton--principal">
          {T.discussion.nouvelle}
        </LienDiscussion>
      </div>
      <Carte titre={T.discussion.listeTitre} id="acp-discussion-liste">
        <p className="acp-discret">{T.discussion.listeIntro}</p>
        {lecture.valeur !== null && lecture.erreur !== null ? (
          <p className="acp-alerte-texte" role="status">
            {T.discussion.listeIndisponible}
          </p>
        ) : null}
        {attente.valeur !== null && !attente.valeur.connu ? (
          // Relecture finale de P7 (constat produit-4) : sans état d'attente lu, l'absence de marque ne prouve rien.
          <p className="acp-alerte-texte" role="status">
            {T.discussion.attenteInconnue}
          </p>
        ) : null}
        {contenu}
      </Carte>
    </div>
  );
}
