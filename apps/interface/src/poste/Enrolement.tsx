// Enrôlement d'un poste (décision D40) : le code à usage unique s'affiche UNE fois, avec « Copier », la commande à
// lancer sur le poste et un compte à rebours ; il n'est gardé que dans l'état de ce composant (jamais stocké) et
// disparaît quand la page change de vue ou se ferme.
import { T } from "../chaines";
import { Donnee } from "../commun";
import { h, useEffect, useState, type Noeud } from "../react";
import { Bouton, RetourEnvoi } from "../projets/briques";
import { useEnvoi } from "../projets/envoi";
import { creerCode } from "./api";
import type { CodeEnrolement } from "./types";

function secondesRestantes(expireLe: unknown, maintenant: number): number | null {
  return typeof expireLe === "number" && Number.isFinite(expireLe) ? Math.max(0, Math.round(expireLe - maintenant / 1000))
    : null;
}

export function Enrolement(props: { apres: () => void }): Noeud {
  const envoi = useEnvoi<CodeEnrolement>();
  const [code, fixerCode] = useState<CodeEnrolement | null>(null);
  const [maintenant, fixerMaintenant] = useState(() => Date.now());
  const [copie, fixerCopie] = useState<"ok" | "impossible" | null>(null);
  useEffect(() => {
    if (!code) return undefined;
    const minuterie = setInterval(() => fixerMaintenant(Date.now()), 1000);
    return () => clearInterval(minuterie);
  }, [code]);
  const generer = async () => {
    fixerCopie(null);
    const resultat = await envoi.envoyer(() => creerCode());
    if (resultat) {
      fixerCode(resultat);
      fixerMaintenant(Date.now());
      props.apres();
    }
  };
  const copier = async () => {
    const presse = globalThis.navigator?.clipboard;
    if (!code?.code || !presse || typeof presse.writeText !== "function") {
      fixerCopie("impossible");
      return;
    }
    try {
      await presse.writeText(code.code);
      fixerCopie("ok");
    } catch {
      fixerCopie("impossible");
    }
  };
  const restant = code ? secondesRestantes(code.expire_le, maintenant) : null;
  const expire = restant !== null && restant <= 0;
  return (
    <div className="acp-groupe">
      <p className="acp-discret" id="acp-poste-enroler-aide">
        {T.poste.enrolerAide}
      </p>
      <div className="acp-actions">
        <Bouton libelle={T.poste.enroler} principal surClic={generer} desactive={envoi.etat.etat === "envoi"}
                decritPar="acp-poste-enroler-aide" />
      </div>
      <RetourEnvoi etat={envoi.etat} />
      {code && !expire ? (
        <div className="acp-code" data-acp-code="">
          <p className="acp-discret">{T.poste.codeTitre}</p>
          <p className="acp-code__valeur">
            <Donnee valeur={code.code} mono />
          </p>
          <p className="acp-discret">{T.poste.codeUneFois}</p>
          <div className="acp-actions">
            <Bouton libelle={T.poste.copier} surClic={copier} />
          </div>
          {copie === "ok" ? <p className="acp-succes" role="status">{T.poste.copie}</p> : null}
          {copie === "impossible" ? <p className="acp-alerte-texte" role="status">{T.poste.copieImpossible}</p> : null}
          <dl className="acp-liste">
            <div className="acp-ligne">
              <dt>{T.poste.commande}</dt>
              <dd>
                <Donnee valeur={code.commande} mono />
              </dd>
            </div>
            <div className="acp-ligne">
              <dt>{T.poste.expireDans}</dt>
              <dd>
                <Donnee valeur={restant} /> <span>{T.poste.secondes}</span>
              </dd>
            </div>
          </dl>
        </div>
      ) : null}
      {code && expire ? <p className="acp-alerte-texte" role="status">{T.poste.codeExpire}</p> : null}
    </div>
  );
}
