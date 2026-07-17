/**
 * Renderer Canvas 2D historique — conservé comme FALLBACK temporaire pendant
 * la migration Phaser. Gelé : corrections de bugs uniquement, aucune évolution.
 */

import type { EntitySpec, RoomSpec, SceneSpec, StationSpec } from "../contracts/scene";
import type { EngineCallbacks, IOfficeRenderer } from "../contracts/renderer";

interface EntityState extends EntitySpec {
  px: number;
  py: number;
  tx: number;
  ty: number;
  wanderAt: number;
  seed: number;
}

const THEMES: Record<string, { floor: string; floorAlt: string; wall: string; accent: string }> = {
  "default": { floor: "#c9b998", floorAlt: "#bfae8c", wall: "#7a6a52", accent: "#5b8266" },
  "dev-floor": { floor: "#9db4c0", floorAlt: "#91a8b4", wall: "#4f6d7a", accent: "#2b6cb0" },
  "data-lab": { floor: "#b8c4bb", floorAlt: "#aab8ae", wall: "#52796f", accent: "#2f9e8f" },
  "library": { floor: "#d4b483", floorAlt: "#c8a878", wall: "#8a5a44", accent: "#a0522d" },
  "game-studio": { floor: "#b39ddb", floorAlt: "#a68fd0", wall: "#5e35b1", accent: "#ff7043" },
};

const DEFAULT_GLYPHS: Record<string, string> = {
  type: "⌨", think: "…", coffee: "☕", sit: "‖", walk: "", away: "zZ",
  read: "📖", write: "✎", chart: "📈", draw: "🎨", play: "🎮", point: "👉",
};

const SKIN = ["#f2c9a0", "#e0ac69", "#c68642", "#8d5524", "#f8d5b8"];
const HAIR = ["#2f2f2f", "#5b3a29", "#a86b32", "#d9b380", "#8c8c8c", "#3a5a8c"];
const SHIRT = ["#e63946", "#457b9d", "#2a9d8f", "#e9c46a", "#9b5de5", "#f4845f", "#3d5a80"];

function hashCode(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export class CanvasRenderer implements IOfficeRenderer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private scene: SceneSpec | null = null;
  private entities: Map<string, EntityState> = new Map();
  private emotes: Map<string, { glyph: string; until: number }> = new Map();
  private roomPulse: Map<string, number> = new Map();
  private selectedId: string | null = null;
  private raf = 0;
  private tile = 16;
  private offsetX = 0;
  private offsetY = 0;

  constructor(private mount: HTMLElement, private callbacks: EngineCallbacks = {}) {
    this.canvas = document.createElement("canvas");
    this.canvas.style.display = "block";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvas.style.imageRendering = "pixelated";
    mount.appendChild(this.canvas);
    const ctx = this.canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas 2D indisponible");
    this.ctx = ctx;
    this.canvas.addEventListener("click", (e) => this.handleClick(e));
    this.loop = this.loop.bind(this);
    this.raf = requestAnimationFrame(this.loop);
  }

  destroy(): void {
    cancelAnimationFrame(this.raf);
    this.canvas.remove();
  }

  setScene(scene: SceneSpec): void {
    this.scene = scene;
    const kept = new Map<string, EntityState>();
    for (const spec of scene.entities) {
      const previous = this.entities.get(spec.id);
      const room = scene.rooms.find((r) => r.id === spec.roomId);
      const home = this.entityHome(spec, room);
      kept.set(spec.id, {
        ...spec,
        px: previous?.px ?? home.x,
        py: previous?.py ?? home.y,
        tx: home.x,
        ty: home.y,
        wanderAt: 0,
        seed: hashCode(spec.name || spec.id),
      });
    }
    this.entities = kept;
    // première frame synchrone : la scène est visible même si rAF est
    // suspendu (onglet en arrière-plan)
    this.fitCanvas();
    this.render(performance.now());
  }

  updateEntityStatus(entityId: string, status: string): void {
    const entity = this.entities.get(entityId);
    if (entity) entity.status = status;
  }

  private static EFFECT_GLYPHS: Record<string, string> = {
    "task-progress": "⚙",
    "task-complete": "✔",
    "task-failed": "✖",
  };

  emote(entityId: string, effectId: string, durationMs = 2500): void {
    // en legacy, les ids d'effets connus sont traduits en glyphes texte ;
    // un glyphe brut reste accepté pendant la migration
    const glyph = CanvasRenderer.EFFECT_GLYPHS[effectId] ?? effectId;
    this.emotes.set(entityId, { glyph, until: performance.now() + durationMs });
  }

  pulseRoom(roomId: string): void {
    this.roomPulse.set(roomId, performance.now() + 1200);
  }

  selectEntity(entityId: string | null): void {
    this.selectedId = entityId;
  }

  focusRoom(_roomId: string): void {
    // pas de caméra en legacy
  }

  zoomStep(_direction: 1 | -1): void {
    // pas de zoom en legacy (vue ajustée automatiquement)
  }

  showGallery(_filterPack?: string): void {
    console.warn("[pixel-office-engine] La galerie n'existe qu'avec le renderer Phaser.");
  }

  // ------------------------------------------------------------------ layout

  private fitCanvas(): void {
    if (!this.scene) return;
    const width = this.mount.clientWidth;
    const height = this.mount.clientHeight;
    if (width === 0 || height === 0) return; // mise en page non calculée (onglet caché)
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.tile = Math.max(8, Math.floor(Math.min(width / this.scene.cols, height / this.scene.rows)));
    this.offsetX = Math.floor((width - this.tile * this.scene.cols) / 2);
    this.offsetY = Math.floor((height - this.tile * this.scene.rows) / 2);
  }

  private entityHome(spec: EntitySpec, room: RoomSpec | undefined): { x: number; y: number } {
    if (!room) return { x: 0, y: 0 };
    const station = spec.stationId
      ? room.stations.find((s) => s.id === spec.stationId)
      : undefined;
    if (station) {
      return { x: room.x + station.x + 0.5, y: room.y + station.y + 1.4 };
    }
    const seed = hashCode(spec.id);
    return {
      x: room.x + 1.5 + (seed % Math.max(1, room.w - 3)),
      y: room.y + 1.5 + ((seed >> 3) % Math.max(1, room.h - 3)),
    };
  }

  // ------------------------------------------------------------------ input

  private handleClick(e: MouseEvent): void {
    if (!this.scene) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - this.offsetX) / this.tile;
    const y = (e.clientY - rect.top - this.offsetY) / this.tile;
    for (const entity of this.entities.values()) {
      if (Math.hypot(entity.px - x, entity.py - y) < 0.8) {
        this.selectedId = entity.id;
        this.callbacks.onEntityClick?.(entity.id);
        return;
      }
    }
    for (const room of this.scene.rooms) {
      if (x >= room.x && x <= room.x + room.w && y >= room.y && y <= room.y + room.h) {
        this.callbacks.onRoomClick?.(room.id);
        return;
      }
    }
  }

  // ------------------------------------------------------------------ update

  private update(now: number): void {
    if (!this.scene) return;
    for (const entity of this.entities.values()) {
      const room = this.scene.rooms.find((r) => r.id === entity.roomId);
      if (!room) continue;
      const animation = this.animationFor(entity.status);
      const anchored = animation !== "walk" && animation !== "coffee" && entity.stationId;
      if (anchored) {
        const home = this.entityHome(entity, room);
        entity.tx = home.x;
        entity.ty = home.y;
      } else if (now > entity.wanderAt) {
        entity.wanderAt = now + 2500 + (entity.seed % 3000);
        entity.tx = room.x + 1.2 + Math.random() * (room.w - 2.4);
        entity.ty = room.y + 1.2 + Math.random() * (room.h - 2.4);
      }
      const dx = entity.tx - entity.px;
      const dy = entity.ty - entity.py;
      const dist = Math.hypot(dx, dy);
      const speed = 0.035;
      if (dist > 0.05) {
        entity.px += (dx / dist) * Math.min(speed, dist);
        entity.py += (dy / dist) * Math.min(speed, dist);
      }
    }
  }

  private animationFor(status: string): string {
    const mapping = this.scene?.statusMapping ?? {};
    return mapping[status] ?? (status === "idle" ? "walk" : "sit");
  }

  // ------------------------------------------------------------------ render

  private loop(now: number): void {
    this.fitCanvas();
    this.update(now);
    this.render(now);
    this.raf = requestAnimationFrame(this.loop);
  }

  private px(v: number): number {
    return Math.round(this.offsetX + v * this.tile);
  }

  private py(v: number): number {
    return Math.round(this.offsetY + v * this.tile);
  }

  private render(now: number): void {
    const { ctx, canvas } = this;
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = "#20242c";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!this.scene) return;
    for (const room of this.scene.rooms) this.drawRoom(room, now);
    const sorted = [...this.entities.values()].sort((a, b) => a.py - b.py);
    for (const entity of sorted) this.drawEntity(entity, now);
  }

  private drawRoom(room: RoomSpec, now: number): void {
    const { ctx, tile } = this;
    const theme = THEMES[room.theme] ?? THEMES["default"];
    for (let i = 0; i < room.w; i++) {
      for (let j = 0; j < room.h; j++) {
        ctx.fillStyle = (i + j) % 2 === 0 ? theme.floor : theme.floorAlt;
        ctx.fillRect(this.px(room.x + i), this.py(room.y + j), tile, tile);
      }
    }
    const wallH = Math.max(3, Math.floor(tile * 0.4));
    ctx.fillStyle = theme.wall;
    ctx.fillRect(this.px(room.x), this.py(room.y), room.w * tile, wallH);
    ctx.strokeStyle = theme.wall;
    ctx.lineWidth = 2;
    ctx.strokeRect(this.px(room.x) + 1, this.py(room.y) + 1, room.w * tile - 2, room.h * tile - 2);
    const pulseUntil = this.roomPulse.get(room.id) ?? 0;
    if (pulseUntil > now) {
      ctx.strokeStyle = theme.accent;
      ctx.lineWidth = 3;
      ctx.globalAlpha = (pulseUntil - now) / 1200;
      ctx.strokeRect(this.px(room.x) - 2, this.py(room.y) - 2, room.w * tile + 4, room.h * tile + 4);
      ctx.globalAlpha = 1;
    }
    for (const station of room.stations) {
      this.drawStation(room, station, theme.accent);
    }
    const fontSize = Math.max(10, Math.floor(tile * 0.55));
    ctx.font = `${fontSize}px monospace`;
    ctx.fillStyle = "#ffffff";
    ctx.textBaseline = "middle";
    ctx.fillText(room.name, this.px(room.x) + 6, this.py(room.y) + wallH / 2 + 1);
    if (room.badge) {
      ctx.font = `${Math.max(9, Math.floor(tile * 0.45))}px monospace`;
      ctx.fillStyle = theme.accent;
      ctx.fillText(room.badge, this.px(room.x) + 6, this.py(room.y + room.h) - fontSize / 2 - 2);
    }
  }

  private drawStation(room: RoomSpec, station: StationSpec, accent: string): void {
    const { ctx, tile } = this;
    const x = this.px(room.x + station.x);
    const y = this.py(room.y + station.y);
    const u = tile / 8;
    switch (station.kind) {
      case "whiteboard":
        ctx.fillStyle = "#f5f5f5";
        ctx.fillRect(x, y + u, tile * 1.6, tile * 0.9);
        ctx.strokeStyle = "#666";
        ctx.strokeRect(x, y + u, tile * 1.6, tile * 0.9);
        ctx.fillStyle = accent;
        ctx.fillRect(x + 2 * u, y + 3 * u, tile * 0.9, u);
        break;
      case "server-rack":
        ctx.fillStyle = "#333a45";
        ctx.fillRect(x, y, tile * 0.9, tile * 1.6);
        for (let k = 0; k < 4; k++) {
          ctx.fillStyle = k % 2 === 0 ? "#57e389" : "#ffbe0b";
          ctx.fillRect(x + 2 * u, y + (2 + k * 3) * u, u, u);
        }
        break;
      case "bookshelf":
        ctx.fillStyle = "#6d4c33";
        ctx.fillRect(x, y, tile * 1.5, tile * 1.4);
        for (let k = 0; k < 5; k++) {
          ctx.fillStyle = ["#c0392b", "#2980b9", "#27ae60", "#f39c12", "#8e44ad"][k];
          ctx.fillRect(x + (1 + k * 2) * u, y + 2 * u, u * 1.5, tile * 0.6);
        }
        break;
      case "couch":
        ctx.fillStyle = "#b3542e";
        ctx.fillRect(x, y + 2 * u, tile * 1.8, tile * 0.8);
        ctx.fillRect(x, y, tile * 0.3, tile);
        ctx.fillRect(x + tile * 1.5, y, tile * 0.3, tile);
        break;
      case "art-station":
        ctx.strokeStyle = "#8d6e63";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x + 2 * u, y + tile * 1.2);
        ctx.lineTo(x + 6 * u, y);
        ctx.lineTo(x + 10 * u, y + tile * 1.2);
        ctx.stroke();
        ctx.fillStyle = "#fffdf5";
        ctx.fillRect(x + 3 * u, y + u, tile * 0.8, tile * 0.7);
        break;
      default: {
        ctx.fillStyle = "#8a6a4b";
        ctx.fillRect(x, y + 3 * u, tile * 1.3, tile * 0.7);
        ctx.fillStyle = "#1d2733";
        ctx.fillRect(x + 2 * u, y, tile * 0.6, tile * 0.5);
        ctx.fillStyle = accent;
        ctx.fillRect(x + 2.5 * u, y + u, tile * 0.45, tile * 0.3);
      }
    }
  }

  private drawEntity(entity: EntityState, now: number): void {
    const { ctx, tile } = this;
    const u = tile / 8;
    const bob = Math.sin(now / 180 + entity.seed) > 0 ? 0 : u;
    const x = this.px(entity.px) - 3 * u;
    const y = this.py(entity.py) - 7 * u + bob;

    const shirt = SHIRT[entity.seed % SHIRT.length];
    const skin = SKIN[entity.seed % SKIN.length];
    const hair = HAIR[(entity.seed >> 4) % HAIR.length];

    if (entity.id === this.selectedId) {
      ctx.strokeStyle = "#ffe066";
      ctx.lineWidth = 2;
      ctx.strokeRect(x - u, y - 2 * u, 8 * u, 12 * u);
    }

    ctx.fillStyle = "rgba(0,0,0,0.25)";
    ctx.fillRect(x + u, y + 8 * u - bob, 4 * u, u);
    ctx.fillStyle = "#2c3e50";
    ctx.fillRect(x + u, y + 6 * u, 1.5 * u, 2 * u);
    ctx.fillRect(x + 3.5 * u, y + 6 * u, 1.5 * u, 2 * u);
    ctx.fillStyle = shirt;
    ctx.fillRect(x + 0.5 * u, y + 3 * u, 5 * u, 3 * u);
    ctx.fillStyle = skin;
    ctx.fillRect(x + u, y, 4 * u, 3 * u);
    ctx.fillStyle = hair;
    ctx.fillRect(x + u, y - 0.5 * u, 4 * u, u);

    if (entity.status === "offline") {
      ctx.fillStyle = "rgba(32,36,44,0.6)";
      ctx.fillRect(x, y - u, 6 * u, 10 * u);
    }

    const emote = this.emotes.get(entity.id);
    const glyphs = { ...DEFAULT_GLYPHS, ...(this.scene?.animationGlyphs ?? {}) };
    const glyph = emote && emote.until > now ? emote.glyph : glyphs[this.animationFor(entity.status)] ?? "";
    if (glyph) {
      ctx.font = `${Math.max(9, Math.floor(tile * 0.5))}px monospace`;
      ctx.textBaseline = "bottom";
      ctx.fillStyle = "#ffffff";
      ctx.fillText(glyph, x + 5 * u, y - u);
    }

    ctx.font = `${Math.max(8, Math.floor(tile * 0.4))}px monospace`;
    ctx.textBaseline = "top";
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.fillText(entity.name, x - u, y + 9 * u);
  }
}
