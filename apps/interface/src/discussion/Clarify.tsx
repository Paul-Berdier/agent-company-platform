// Question « clarify » de Hermes (cahier P7 § 9.2) : une question seule ou un lot ; choix en boutons (la marque
// « recommandé » de Hermes dite en français), plusieurs choix si Hermes le permet, champ libre qui l'emporte s'il est
// rempli ; « Répondre » envoie toute la demande en une fois ({ answer } ou { answers }, conversation.ts).
import { T } from "../chaines";
import { Carte, Donnee } from "../commun";
import { Bouton } from "../projets/briques";
import { h, useState, type Noeud } from "../react";
import { texteDeReponse, type DemandeClarify, type QuestionClarify, type Saisie } from "./conversation";

function idDe(demande: DemandeClarify, rang: number, suffixe: string): string {
  return `acp-clarify-${demande.id.replace(/[^A-Za-z0-9_-]/g, "_")}-${rang}-${suffixe}`;
}

function Question(props: { demande: DemandeClarify; question: QuestionClarify; rang: number; saisie: Saisie;
                           changer: (saisie: Saisie) => void }): Noeud {
  const { demande, question, rang, saisie } = props;
  const basculer = (valeur: string) => {
    const deja = saisie.choix.includes(valeur);
    const choix = question.multiple
      ? (deja ? saisie.choix.filter((c) => c !== valeur) : [...saisie.choix, valeur])
      : (deja ? [] : [valeur]);
    props.changer({ ...saisie, choix });
  };
  const aide = idDe(demande, rang, "aide");
  return (
    <fieldset className="acp-groupe-choix acp-clarify__question">
      <legend>
        <Donnee valeur={question.texte} />
      </legend>
      {question.dejaRepondu !== null ? (
        <p className="acp-discret">
          <span>{T.discussion.dejaRepondu}</span> <Donnee valeur={question.dejaRepondu} />
        </p>
      ) : null}
      {question.choix.length > 0 ? (
        <div className="acp-actions">
          {question.choix.map((c) => (
            <button key={c.valeur} type="button" className="acp-bouton acp-choix-bouton"
                    aria-pressed={saisie.choix.includes(c.valeur) ? "true" : "false"}
                    onClick={() => basculer(c.valeur)}>
              <Donnee valeur={c.libelle} />
              {c.recommande ? <span className="acp-discret">{T.discussion.recommande}</span> : null}
            </button>
          ))}
        </div>
      ) : null}
      {question.multiple && question.choix.length > 0 ? <p className="acp-discret">{T.discussion.choixMultiple}</p> : null}
      <div className="acp-champ">
        <label htmlFor={idDe(demande, rang, "libre")}>{T.discussion.reponseLibre}</label>
        <textarea id={idDe(demande, rang, "libre")} rows={2} maxLength={4000} value={saisie.libre}
                  aria-describedby={question.choix.length > 0 ? aide : undefined}
                  onChange={(e: { target: { value: string } }) => props.changer({ ...saisie, libre: e.target.value })} />
        {question.choix.length > 0 ? <p className="acp-discret" id={aide}>{T.discussion.reponseLibreAide}</p> : null}
      </div>
    </fieldset>
  );
}

export function Clarify(props: { demande: DemandeClarify; actif: boolean;
                                 repondre: (id: string, saisies: Record<string, Saisie>) => boolean;
                                 brouillon?: Record<string, Saisie>;
                                 garder?: (saisies: Record<string, Saisie>) => void }): Noeud {
  const { demande } = props;
  const [saisies, fixerSaisies] = useState<Record<string, Saisie>>(() => {
    // Saisie gardée par la page (même requête, carte remontée après une reconnexion) : reprise telle quelle.
    if (props.brouillon) return props.brouillon;
    const initiales: Record<string, Saisie> = {};
    demande.questions.forEach((q, rang) => {
      initiales[String(rang)] = { choix: [], libre: q.dejaRepondu ?? "" };
    });
    return initiales;
  });
  const fixer = (changer: (avant: Record<string, Saisie>) => Record<string, Saisie>) =>
    fixerSaisies((avant) => {
      const suivant = changer(avant);
      props.garder?.(suivant);
      return suivant;
    });
  const [envoyee, fixerEnvoyee] = useState(false);
  const vide = demande.questions.every((q, rang) => texteDeReponse(q, saisies[String(rang)]) === "");
  const titre = demande.questions.length > 1 ? T.discussion.questionsTitre : T.discussion.questionTitre;
  const surEnvoi = (evenement: { preventDefault(): void }) => {
    evenement.preventDefault();
    if (vide || envoyee || !props.actif) return;
    fixerEnvoyee(props.repondre(demande.id, saisies));
  };
  return (
    <Carte titre={titre} id={idDe(demande, 0, "titre")}>
      <form className="acp-formulaire acp-clarify" onSubmit={surEnvoi} data-acp-clarify={demande.id}>
        {demande.questions.map((q, rang) => (
          <Question key={`${demande.id}-${rang}`} demande={demande} question={q} rang={rang}
                    saisie={saisies[String(rang)] ?? { choix: [], libre: "" }}
                    changer={(saisie) => fixer((avant) => ({ ...avant, [String(rang)]: saisie }))} />
        ))}
        <div className="acp-actions">
          <Bouton libelle={T.discussion.repondre} type="submit" principal desactive={vide || envoyee || !props.actif} />
        </div>
      </form>
    </Carte>
  );
}
