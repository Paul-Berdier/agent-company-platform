import { describe, expect, it } from "vitest";

import { StationReservations, type SeatPosition } from "../src/phaser/grid/reservations";

const SEATS: SeatPosition[] = [
  { x: 5, y: 5, facing: "up" },
  { x: 6, y: 5, facing: "up" },
];

describe("StationReservations", () => {
  it("attribue un siège par agent, dans l'ordre", () => {
    const r = new StationReservations();
    expect(r.reserve("a", "desk-1", SEATS)?.seat).toEqual(SEATS[0]);
    expect(r.reserve("b", "desk-1", SEATS)?.seat).toEqual(SEATS[1]);
    expect(r.occupancy("desk-1")).toBe(2);
  });

  it("refuse quand la station est complète", () => {
    const r = new StationReservations();
    r.reserve("a", "desk-1", SEATS);
    r.reserve("b", "desk-1", SEATS);
    expect(r.reserve("c", "desk-1", SEATS)).toBeNull();
  });

  it("est idempotent pour un agent déjà assis", () => {
    const r = new StationReservations();
    const first = r.reserve("a", "desk-1", SEATS);
    const again = r.reserve("a", "desk-1", SEATS);
    expect(again).toEqual(first);
    expect(r.occupancy("desk-1")).toBe(1);
  });

  it("libère l'ancien siège quand un agent change de station", () => {
    const r = new StationReservations();
    r.reserve("a", "desk-1", SEATS);
    r.reserve("a", "desk-2", SEATS);
    expect(r.occupancy("desk-1")).toBe(0);
    expect(r.occupancy("desk-2")).toBe(1);
    expect(r.reservationOf("a")?.stationKey).toBe("desk-2");
  });

  it("release rend le siège disponible", () => {
    const r = new StationReservations();
    r.reserve("a", "desk-1", SEATS);
    r.reserve("b", "desk-1", SEATS);
    r.release("a");
    expect(r.reserve("c", "desk-1", SEATS)?.seat).toEqual(SEATS[0]);
  });

  it("clear repart de zéro", () => {
    const r = new StationReservations();
    r.reserve("a", "desk-1", SEATS);
    r.clear();
    expect(r.occupancy("desk-1")).toBe(0);
    expect(r.reservationOf("a")).toBeNull();
  });
});
