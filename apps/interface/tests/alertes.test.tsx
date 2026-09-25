import { beforeEach, describe, expect, it } from "vitest";
import { h } from "../src/react";
import { Alertes } from "../src/interface/Alertes";
import { Marque } from "../src/interface/Marque";
import { creerRefus } from "../src/refus";
import { oublierMeta, ROUTE_META } from "../src/api";
import { CATALOGUE } from "./catalogue-chaines";
import { META } from "./fixtures";
import { ApiErrorHermes, installerSdk, rendre, textesHorsCatalogue } from "./sdk-factice";

beforeEach(() => oublierMeta());

describe("bannière d'alertes", () => {
  it("ne rend rien sans alerte", async () => {
    installerSdk({ [ROUTE_META]: META });
    const r = await rendre(<Alertes />);
    expect(r.racine.innerHTML).toBe("");
    r.demonter();
  });

  it("liste les alertes de /v1/meta comme données", async () => {
    const alertes = [
      "SOUL.md a été modifié par le propriétaire : la persona livrée n'est pas appliquée.",
      "Hermes 0.22.0 n'est pas la version testée (0.21.5).",
    ];
    installerSdk({ [ROUTE_META]: { ...META, alertes } });
    const r = await rendre(<Alertes />);
    const elements = [...r.racine.querySelectorAll("li [data-acp-donnee]")].map((e) => e.textContent);
    expect(elements).toEqual(alertes);
    expect(r.racine.querySelector("h2")?.textContent).toBe("Alertes ACP");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });

  it("signale une méta injoignable", async () => {
    installerSdk({
      [ROUTE_META]: new ApiErrorHermes("The Hermes service is not ready yet.", 503, '{"detail":"Service Unavailable"}'),
    });
    const r = await rendre(<Alertes />);
    expect(r.texte()).toContain("L'état de la plateforme est indisponible");
    expect(r.texte()).toContain("503");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});

describe("marque", () => {
  it("logotype texte ACP, lien accessible vers l'accueil", async () => {
    installerSdk();
    window.__HERMES_BASE_PATH__ = "/base/";
    const r = await rendre(<Marque />);
    const lien = r.racine.querySelector("a");
    expect(lien?.getAttribute("href")).toBe("/base/");
    expect(lien?.getAttribute("aria-label")).toBe("ACP, retour à l'accueil");
    expect(lien?.textContent).toBe("ACP");
    r.demonter();
  });
});

describe("refus du SDK", () => {
  it("dit en français que l'interface est désactivée, avec la version trouvée", async () => {
    installerSdk();
    const Refus = creerRefus("2.0.0");
    const r = await rendre(<Refus />);
    expect(r.racine.querySelector("[role='alert']")).not.toBeNull();
    expect(r.texte()).toContain("Interface ACP désactivée : SDK du tableau de bord incompatible.");
    expect(r.texte()).toContain("1.x");
    expect(r.texte()).toContain("2.0.0");
    expect(textesHorsCatalogue(r.racine, CATALOGUE)).toEqual([]);
    r.demonter();
  });
});
