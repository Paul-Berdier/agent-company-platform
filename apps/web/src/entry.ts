import { resolveAmbientView } from "./ambient-config";

const params = new URLSearchParams(location.search);
const ambientView = resolveAmbientView(location.pathname, params.get("view"));

if (ambientView) {
  const stage = document.createElement("div");
  stage.id = "ambient-stage";
  const overlay = document.createElement("div");
  overlay.id = "ambient-overlay";
  document.body.replaceChildren(stage, overlay);
  void import("./ambient");
} else {
  void import("./main");
}
