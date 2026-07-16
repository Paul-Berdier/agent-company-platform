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

export class StationReservations {
  private seatsByStation = new Map<string, Map<number, string>>();
  private byEntity = new Map<string, Reservation>();

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

  release(entityId: string): void {
    const reservation = this.byEntity.get(entityId);
    if (!reservation) return;
    this.byEntity.delete(entityId);
    this.seatsByStation.get(reservation.stationKey)?.delete(reservation.seatIndex);
  }

  reservationOf(entityId: string): Reservation | null {
    return this.byEntity.get(entityId) ?? null;
  }

  occupancy(stationKey: string): number {
    return this.seatsByStation.get(stationKey)?.size ?? 0;
  }

  clear(): void {
    this.seatsByStation.clear();
    this.byEntity.clear();
  }
}
