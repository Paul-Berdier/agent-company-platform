// Une discussion (cahier P7 § 9.2) : messages repris, réponse de Hermes en flux (texte brut, retours à la ligne gardés,
// aucun HTML interprété), une ligne d'état, les questions « clarify » (Clarify.tsx), « Envoyer » et « Interrompre ».
// Toute la logique vit dans conversation.ts ; ce composant ne fait que la montrer et lui transmettre les gestes.
import { T } from "../chaines";
import { Donnee } from "../commun";
import { Bouton } from "../projets/briques";
import { h, useEffect, useRef, useState, type Noeud } from "../react";
import { Clarify } from "./Clarify";
import {
  Conversation,
  etatInitial,
  TEXTE_MAX,
  type EtatConversation,
  type MessageFil,
  type OuvrirCanal,
  type Saisie,
} from "./conversation";
import { LienDiscussion } from "./Liste";
import type { NaviguerDiscussion } from "./vue";

/** Conversation de la page : créée au montage, arrêtée au démontage (la session reste vivante dans Hermes). */
export function useConversation(cle: string | null, surCle: (cle: string) => void,
                                ouvrir?: OuvrirCanal): [EtatConversation, Conversation | null] {
  const conversation = useRef<Conversation | null>(null);
  const [etat, fixer] = useState<EtatConversation | null>(null);
  const rappel = useRef(surCle);
  rappel.current = surCle;
  useEffect(() => {
    const c = new Conversation({ cle, surCle: (k) => rappel.current(k), ouvrir });
    conversation.current = c;
    fixer(c.etat());
    const desabonner = c.abonner(fixer);
    c.demarrer();
    const surVisibilite = () => {
      if (document.visibilityState !== "hidden") c.reveiller();
    };
    document.addEventListener("visibilitychange", surVisibilite);
    return () => {
      document.removeEventListener("visibilitychange", surVisibilite);
      desabonner();
      c.arreter();
      conversation.current = null;
    };
  }, [cle]);
  return [etat ?? conversation.current?.etat() ?? etatInitial(cle), conversation.current];
}

function Connexion(props: { etat: EtatConversation; naviguer: NaviguerDiscussion }): Noeud {
  const { etat } = props;
  if (etat.connexion === "indisponible") {
    return (
      <p className="acp-alerte-texte" role="alert" data-acp-connexion={etat.connexion}>
        {T.discussion.indisponible}
      </p>
    );
  }
  if (etat.connexion === "introuvable") {
    return (
      <div className="acp-erreur" role="alert" data-acp-connexion={etat.connexion}>
        <p>{T.discussion.introuvable}</p>
        <p>
          <LienDiscussion vue={{ genre: "liste" }} naviguer={props.naviguer}>
            {T.discussion.retourListe}
          </LienDiscussion>
        </p>
      </div>
    );
  }
  if (etat.connexion === "session_expiree") {
    // Relecture finale de P7 (constat produit-3) : recharger la page passe par la porte d'authentification de Hermes,
    // qui ramène sur cette discussion après la connexion (paramètre « next »).
    const ici = typeof window === "undefined" ? "" : `${window.location.pathname}${window.location.search}`;
    return (
      <div className="acp-erreur" role="alert" data-acp-connexion={etat.connexion}>
        <p>{T.discussion.sessionExpiree}</p>
        <p>
          <a className="acp-lien" href={ici}>
            {T.discussion.recharger}
          </a>
        </p>
      </div>
    );
  }
  if (etat.connexion === "reconnexion") {
    // Tentative en cours (aucun délai à annoncer) : dite telle quelle, jamais « dans Inconnu s » (constat produit-5).
    return (
      <p className="acp-alerte-texte" role="status" data-acp-connexion={etat.connexion}>
        {etat.tentativeDans === null ? (
          <span>{T.discussion.reconnexionEnCours}</span>
        ) : (
          <span>
            <span>{T.discussion.reconnexion}</span> <Donnee valeur={etat.tentativeDans} />{" "}
            <span>{T.discussion.secondes}</span>
          </span>
        )}
      </p>
    );
  }
  return (
    <p className="acp-discret" role="status" data-acp-connexion={etat.connexion}>
      {etat.connexion === "prete" ? T.discussion.prete : T.discussion.connexion}
    </p>
  );
}

function Bulle(props: { message: MessageFil }): Noeud {
  const m = props.message;
  if (m.role === "outil") {
    return (
      <li className="acp-bulle acp-bulle--outil">
        <span>{T.discussion.outil}</span> <Donnee valeur={m.texte} mono />
      </li>
    );
  }
  const auteur = m.role === "utilisateur" ? T.discussion.vous : m.role === "hermes" ? T.discussion.hermes
    : T.discussion.erreurHermes;
  return (
    <li className={`acp-bulle acp-bulle--${m.role}`} aria-busy={m.enCours ? "true" : undefined}
        data-acp-message={m.role}>
      <span className="acp-bulle__auteur">{auteur}</span>
      {m.texte ? (
        <p className="acp-bulle__texte">
          <Donnee valeur={m.texte} />
        </p>
      ) : m.enCours ? (
        <p className="acp-discret">{T.discussion.enCours}</p>
      ) : null}
      {m.fin === "interrupted" ? <p className="acp-discret">{T.discussion.interrompu}</p> : null}
      {m.fin === "error" ? <p className="acp-alerte-texte">{T.discussion.echoue}</p> : null}
    </li>
  );
}

export function Fil(props: { cle: string | null; naviguer: NaviguerDiscussion; surCle: (cle: string) => void;
                             ouvrir?: OuvrirCanal }): Noeud {
  const [etat, conversation] = useConversation(props.cle, props.surCle, props.ouvrir);
  // Réponses en cours de saisie des questions « clarify », par identifiant de requête : une reconnexion démonte puis
  // remonte la carte (même identifiant, rejouée par session.resume) ; la saisie survit (constat produit-13).
  const brouillons = useRef(new Map<string, Record<string, Saisie>>());
  const [texte, fixerTexte] = useState("");
  const [envoi, fixerEnvoi] = useState(false);
  const fin = useRef<HTMLDivElement | null>(null);
  const nombre = etat.messages.length + etat.demandes.length;
  useEffect(() => {
    // Le dernier message (ou la question qui arrive) reste en vue au téléphone.
    try {
      fin.current?.scrollIntoView?.({ block: "nearest" });
    } catch {
      // Défilement impossible : sans effet.
    }
  }, [nombre]);
  const prete = etat.connexion === "prete";
  const peutEnvoyer = prete && !etat.enCours && !envoi && texte.trim() !== "";
  const surEnvoi = async (evenement: { preventDefault(): void }) => {
    evenement.preventDefault();
    if (!conversation || !peutEnvoyer) return;
    fixerEnvoi(true);
    const accepte = await conversation.envoyer(texte);
    fixerEnvoi(false);
    if (accepte) fixerTexte("");
  };
  const refusees = [...new Set(etat.refusees)];
  return (
    <div className="acp-sections">
      <nav className="acp-actions" aria-label={T.discussion.navigation}>
        <LienDiscussion vue={{ genre: "liste" }} naviguer={props.naviguer}>
          {T.discussion.retourListe}
        </LienDiscussion>
      </nav>
      <section className="acp-carte" aria-labelledby="acp-discussion-titre">
        <h2 className="acp-carte__titre acp-carte__titre--grand" id="acp-discussion-titre">
          {etat.titre ? <Donnee valeur={etat.titre} /> : <span>{etat.cle ? T.discussion.sansTitre : T.discussion.nouvelle}</span>}
        </h2>
        <Connexion etat={etat} naviguer={props.naviguer} />
        {etat.cle === null && etat.messages.length === 0 ? <p className="acp-discret">{T.discussion.nouvelleIntro}</p> : null}
        {etat.messages.length > 0 ? (
          <ol className="acp-fil" aria-label={T.discussion.fil}>
            {etat.messages.map((m) => (
              <Bulle key={m.id} message={m} />
            ))}
          </ol>
        ) : null}
        {etat.ligneEtat ? (
          <p className="acp-discret" role="status">
            <span>{T.discussion.etat}</span> <Donnee valeur={etat.ligneEtat} />
          </p>
        ) : null}
        {refusees.map((methode) => (
          <p key={`refus-${methode}`} className="acp-alerte-texte" role="alert">
            <span>{T.discussion.refusee}</span> <span>{T.discussion.demande}</span> <Donnee valeur={methode} mono />
          </p>
        ))}
        {etat.retirees.length > 0 ? (
          <p className="acp-discret" role="status">
            <span>{T.discussion.retiree}</span> <span>{T.discussion.raison}</span>{" "}
            <Donnee valeur={etat.retirees[etat.retirees.length - 1]} mono />
          </p>
        ) : null}
      </section>
      {etat.demandes.map((d) => (
        <Clarify key={d.id} demande={d} actif={prete} brouillon={brouillons.current.get(d.id)}
                 garder={(saisies) => brouillons.current.set(d.id, saisies)}
                 repondre={(id, saisies) => {
                   const envoyee = conversation?.repondre(id, saisies) ?? false;
                   if (envoyee) brouillons.current.delete(id);
                   return envoyee;
                 }} />
      ))}
      {etat.erreur ? (
        <div className="acp-erreur" role="alert">
          <p>{T.discussion.erreurs[etat.erreur.genre]}</p>
          {etat.erreur.detail ? (
            <details className="acp-details">
              <summary>{T.commun.detailTechnique}</summary>
              <Donnee valeur={etat.erreur.detail} mono />
            </details>
          ) : null}
        </div>
      ) : null}
      <form className="acp-carte acp-formulaire" onSubmit={surEnvoi}>
        <div className="acp-champ">
          <label htmlFor="acp-discussion-message">{T.discussion.message}</label>
          <textarea id="acp-discussion-message" rows={3} maxLength={TEXTE_MAX} value={texte}
                    onChange={(e: { target: { value: string } }) => fixerTexte(e.target.value)} />
        </div>
        {etat.enCours ? <p className="acp-discret">{T.discussion.tourEnCours}</p> : null}
        <div className="acp-actions">
          <Bouton libelle={T.discussion.envoyer} type="submit" principal desactive={!peutEnvoyer} />
          {etat.enCours && etat.sessionId ? (
            <Bouton libelle={T.discussion.interrompre} danger desactive={!prete}
                    surClic={() => void conversation?.interrompre()} />
          ) : null}
        </div>
      </form>
      <div ref={fin} />
    </div>
  );
}
