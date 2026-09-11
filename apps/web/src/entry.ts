import { resolveAmbientView } from "./ambient-config";

const params = new URLSearchParams(location.search);
const ambientView = resolveAmbientView(location.pathname, params.get("view"));
const legacyOfficeEnabled = params.get("legacy-office") === "1"
  || import.meta.env.VITE_ACP_LEGACY_OFFICE === "1";

if (ambientView) {
  const stage = document.createElement("div");
  stage.id = "ambient-stage";
  const overlay = document.createElement("div");
  overlay.id = "ambient-overlay";
  document.body.replaceChildren(stage, overlay);
  void import("./ambient");
} else if (legacyOfficeEnabled) {
  void import("./main");
} else {
  void import("./workspace");
}
