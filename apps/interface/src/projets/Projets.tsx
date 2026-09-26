// Page « Projets » (greffon acp-projets, étape P4 ; cahier P4 § 15), pensée d'abord pour le téléphone :
// lancer un projet, suivre son avancement, répondre aux questions, mettre en pause.
//
// Aucune route propre : tout passe par les routes d'acp-poste (docs/refonte/projets.md § 4), derrière la
// session du tableau de bord. Chaque bouton appelle une route réelle et testée ; aucune donnée
// inventée (« Inconnu », « Non configuré », « Non observé ») ; sondage de 15 s tant que la page est
// visible (D35).
import { T } from "../chaines";
import { BlocErreur, Donnee, EnChargement } from "../commun";
import { h, useRef, useState, type Noeud } from "../react";
import { lireProjets } from "./api";
import { BandeauPause } from "./BandeauPause";
import { LienVue } from "./briques";
import { DetailProjet } from "./DetailProjet";
import { ListeProjets } from "./ListeProjets";
import { NouveauProjet } from "./NouveauProjet";
import { Questions } from "./Questions";
import { useSondage } from "./sondage";
import { memeVue, remplacerAdresse, vueDepuisAdresse, type Vue } from "./vue";

function Navigation(props: { vue: Vue; naviguer: (v: Vue) => void; questions: number | null }): Noeud {
  const onglets: Array<{ vue: Vue; libelle: string; compte?: number | null }> = [
    { vue: { genre: "liste" }, libelle: T.projets.vueListe },
    { vue: { genre: "questions" }, libelle: T.projets.vueQuestions, compte: props.questions },
    { vue: { genre: "nouveau" }, libelle: T.projets.vueNouveau },
  ];
  return (
    <nav className="acp-onglets" aria-label={T.projets.navigation}>
      {onglets.map((o) => (
        <LienVue
          key={o.vue.genre}
          vue={o.vue}
          naviguer={props.naviguer}
          className="acp-onglet"
          courant={memeVue(o.vue, props.vue) || (o.vue.genre === "liste" && props.vue.genre === "detail")}
        >
          <span>{o.libelle}</span>
          {typeof o.compte === "number" && o.compte > 0 ? (
            <span className="acp-compteur">
              <Donnee valeur={o.compte} />
            </span>
          ) : null}
        </LienVue>
      ))}
    </nav>
  );
}

export function Projets(): Noeud {
  const [vue, fixerVue] = useState<Vue>(() => vueDepuisAdresse(window.location.search));
  // Incrémenté après chaque geste : toutes les lectures de la page se refont aussitôt.
  const [jeton, fixerJeton] = useState(0);
  const rafraichir = () => fixerJeton((j) => j + 1);
  const liste = useSondage(lireProjets, jeton);
  const racine = useRef<HTMLDivElement | null>(null);
  const naviguer = (suivante: Vue) => {
    fixerVue(suivante);
    remplacerAdresse(suivante);
    rafraichir();
    // Hermes fait défiler ses pages dans un conteneur interne (pas la fenêtre) : la nouvelle vue repart du
    // haut de la page, sinon, au téléphone, le détail d'un projet lancé s'ouvrirait au niveau du bouton.
    try {
      racine.current?.scrollIntoView?.({ block: "start" });
    } catch {
      // Défilement impossible : sans effet sur la vue.
    }
  };
  const donnees = liste.valeur;
  const questions = typeof donnees?.questions_ouvertes === "number" ? donnees.questions_ouvertes : null;
  const pause = donnees?.pause_generale && typeof donnees.pause_generale === "object" ? donnees.pause_generale : null;

  return (
    <div className="acp-page" data-acp-racine="projets" ref={racine}>
      <div className="acp-entete">
        <h1 className="acp-titre">{T.projets.titre}</h1>
        <p className="acp-discret">{T.projets.intro}</p>
      </div>
      <Navigation vue={vue} naviguer={naviguer} questions={questions} />
      {pause ? <BandeauPause pause={pause} apres={rafraichir} /> : null}
      {donnees === null && liste.erreur === null ? <EnChargement /> : null}
      {donnees === null && liste.erreur !== null ? <BlocErreur erreur={liste.erreur} message={T.projets.indisponible} /> : null}
      {donnees !== null && liste.erreur !== null ? (
        <p className="acp-alerte-texte" role="status">
          {T.projets.actualisationImpossible}
        </p>
      ) : null}
      {vue.genre === "liste" && donnees !== null ? (
        <ListeProjets donnees={donnees} naviguer={naviguer} apres={rafraichir} />
      ) : null}
      {vue.genre === "nouveau" ? <NouveauProjet naviguer={naviguer} apres={rafraichir} /> : null}
      {vue.genre === "detail" ? (
        <DetailProjet key={vue.id} id={vue.id} jeton={jeton} liste={donnees} naviguer={naviguer} apres={rafraichir} />
      ) : null}
      {vue.genre === "questions" ? <Questions jeton={jeton} naviguer={naviguer} apres={rafraichir} /> : null}
      <p className="acp-discret">{T.projets.actualisation}</p>
    </div>
  );
}
