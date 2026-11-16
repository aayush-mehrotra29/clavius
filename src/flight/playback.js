// Use animation-frame timestamps throughout. The first callback's timestamp
// can predate setup, since all callbacks for a frame share the same timestamp.
export function advanceSample(index, previousFrame, frame, rate, count) {
  const seconds = Math.max(0, Math.min((frame - (previousFrame ?? frame)) / 1000, 0.25));
  return (index + seconds * rate) % count;
}
