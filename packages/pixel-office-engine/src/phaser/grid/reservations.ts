/**
 * Réservation des sièges de stations : un siège = un agent.
 * Module pur (aucun import Phaser), couvert par les tests.
 */

import type { Facing } from "../../contracts/scene";

export interface SeatPosition {
  x: number; // tuiles absolues
  y: number;
  facing: Facing;
}

export interface Reservation {
  stationKey: string;
  seatIndex: number;
  seat: SeatPosition;
}

export type SeatOrQueue =
  | { kind: "seat"; reservation: Reservation }
  | { kind: "queued"; position: number };

export class StationReservations {
  private seatsByStation = new Map<string, Map<number, string>>();
  private byEntity = new Map<string, Reservation>();
  private queues = new Map<string, string[]>();

  /**
   * Réserve un siège de la station pour l'entité. Idempotent : si l'entité
   * détient déjà un siège de cette station, il est conservé.
   * Retourne null si la station est complète.
   */
  reserve(entityId: string, stationKey: string, seats: SeatPosition[]): Reservation | null {
    const existing = this.byEntity.get(entityId);
    if (existing && existing.stationKey === stationKey) return existing;
    if (existing) this.release(entityId);

    let taken = this.seatsByStation.get(stationKey);
    if (!taken) {
      taken = new Map();
      this.seatsByStation.set(stationKey, taken);
    }
    for (let index = 0; index < seats.length; index++) {
      if (!taken.has(index)) {
        taken.set(index, entityId);
        const reservation: Reservation = { stationKey, seatIndex: index, seat: seats[index] };
        this.byEntity.set(entityId, reservation);
        return reservation;
      }
    }
    return null;
  }

  /**
   * Réserve un siège ou place l'agent en file d'attente (ordonnée).
   * Le siège libéré revient toujours à la tête de file.
   */
  reserveOrQueue(entityId: string, stationKey: string, seats: SeatPosition[]): SeatOrQueue {
    const existing = this.byEntity.get(entityId);
    if (existing && existing.stationKey === stationKey) {
      return { kind: "seat", reservation: existing };
    }
    const queue = this.queues.get(stationKey) ?? [];
    const occupied = this.seatsByStation.get(stationKey)?.size ?? 0;
    const isHead = queue.length === 0 || queue[0] === entityId;

    if (occupied < seats.length && isHead) {
      if (queue[0] === entityId) queue.shift();
      this.queues.set(stationKey, queue);
      const reservation = this.reserve(entityId, stationKey, seats);
      if (reservation) return { kind: "seat", reservation };
    }
    if (existing) this.release(entityId); // il attend : il n'occupe plus son ancien siège
    if (!queue.includes(entityId)) queue.push(entityId);
    this.queues.set(stationKey, queue);
    return { kind: "queued", position: queue.indexOf(entityId) };
  }

  release(entityId: string): void {
    const reservation = this.byEntity.get(entityId);
    if (reservation) {
      this.byEntity.delete(entityId);
      this.seatsByStation.get(reservation.stationKey)?.delete(reservation.seatIndex);
    }
    for (const queue of this.queues.values()) {
      const index = queue.indexOf(entityId);
      if (index >= 0) queue.splice(index, 1);
    }
  }

  reservationOf(entityId: string): Reservation | null {
    return this.byEntity.get(entityId) ?? null;
  }

  occupancy(stationKey: string): number {
    return this.seatsByStation.get(stationKey)?.size ?? 0;
  }

  queueLength(stationKey: string): number {
    return this.queues.get(stationKey)?.length ?? 0;
  }

  clear(): void {
    this.seatsByStation.clear();
    this.byEntity.clear();
    this.queues.clear();
  }
}
