/**
 * Convertit une carte Tiled (.tmj, export JSON) en template de salle
 * (`plugins/<module>/rooms/<id>.json`).
 *
 * Convention Tiled :
 * - propriétés de carte : `id`, `department_type`, `theme`, `capacity` ;
 * - calque d'objets "stations" : un objet par station, `name` = kind,
 *   propriétés optionnelles `id`, `label` ;
 * - calque d'objets "doors" : un objet par porte ;
 * - calque d'objets "windows" : un objet par fenêtre (seul x compte).
 *
 * Usage : node tools/tiled-to-template.mjs <carte.tmj> <sortie.json>
 */

import fs from "node:fs";

const [, , inFile, outFile] = process.argv;
if (!inFile || !outFile) {
  console.error("Usage: node tools/tiled-to-template.mjs <carte.tmj> <sortie.json>");
  process.exit(2);
}

const map = JSON.parse(fs.readFileSync(inFile, "utf-8"));
if (map.orientation !== "orthogonal" || map.tilewidth !== 32 || map.tileheight !== 32) {
  console.error("Carte attendue : orthogonale, tuiles 32×32 (Tiled ≥ 1.10, export JSON)");
  process.exit(1);
}

const mapProps = Object.fromEntries((map.properties ?? []).map((p) => [p.name, p.value]));
const objectLayer = (name) =>
  map.layers.find((l) => l.type === "objectgroup" && l.name === name)?.objects ?? [];

const toTile = (v) => Math.round(v / 32);

const stations = objectLayer("stations").map((object, index) => {
  const props = Object.fromEntries((object.properties ?? []).map((p) => [p.name, p.value]));
  return {
    id: props.id ?? `${object.name}-${index + 1}`,
    name: props.label ?? object.name,
    kind: object.name,
    x: toTile(object.x),
    // Tiled ancre les objets-tuiles en bas : remonter d'une tuile
    y: toTile(object.y) - (object.gid ? 1 : 0),
  };
});

const doors = objectLayer("doors").map((o) => ({ x: toTile(o.x), y: toTile(o.y) }));
const windows = objectLayer("windows").map((o) => toTile(o.x));

const template = {
  id: mapProps.id ?? inFile.replace(/.*[\\/]/, "").replace(/\.tmj$/i, ""),
  schema_version: "1.0",
  department_type: mapProps.department_type ?? null,
  name: mapProps.name ?? "",
  theme: mapProps.theme ?? "default",
  width: map.width,
  height: map.height,
  capacity: Number(mapProps.capacity ?? 4),
  doors,
  windows,
  stations,
  upgrade_to: mapProps.upgrade_to ?? null,
};

if (stations.length === 0) console.warn("⚠ aucun objet dans le calque \"stations\"");
fs.writeFileSync(outFile, JSON.stringify(template, null, 2));
console.log(`OK → ${outFile} (${stations.length} stations, ${doors.length} porte(s))`);
