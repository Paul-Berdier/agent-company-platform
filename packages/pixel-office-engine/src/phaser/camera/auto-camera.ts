export function autoCameraDelay(intervalMs: number | undefined): number {
  return Math.max(1000, intervalMs ?? 9000);
}

export function nextAutoCameraIndex(current: number, roomCount: number): {
  roomIndex: number;
  nextIndex: number;
} | null {
  if (roomCount <= 0) return null;
  return { roomIndex: current % roomCount, nextIndex: current + 1 };
}
