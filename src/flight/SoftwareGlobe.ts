import * as THREE from 'three';
import {globeBounds, mapPixel} from './globe-projection.js';

export class SoftwareGlobe {
  private readonly maps = new WeakMap<HTMLImageElement, ImageData>();
  private readonly tile = document.createElement('canvas');
  private readonly tileContext = this.tile.getContext('2d')!;
  private readonly normal = new THREE.Vector3();
  private readonly cameraToLocal = new THREE.Quaternion();

  private pixels(image: HTMLImageElement) {
    const stored = this.maps.get(image);
    if (stored) return stored;
    const canvas = document.createElement('canvas');
    canvas.width = Math.min(2048, image.naturalWidth);
    canvas.height = canvas.width / 2;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
    this.maps.set(image, pixels);
    return pixels;
  }

  draw(ctx: CanvasRenderingContext2D, width: number, height: number,
       body: THREE.Mesh, camera: THREE.PerspectiveCamera, center: THREE.Vector3,
       radius: number, focal: number, sunCamera: THREE.Vector3, image?: HTMLImageElement) {
    const box = globeBounds(center, radius, focal, width, height);
    if (box.width < 1 || box.height < 1) return;
    // Bound the software workload when the camera zooms close to a globe.
    const scale = Math.min(1, 320 / Math.max(box.width, box.height));
    const w = Math.max(1, Math.ceil(box.width * scale)), h = Math.max(1, Math.ceil(box.height * scale));
    if (this.tile.width !== w || this.tile.height !== h) {
      this.tile.width = w;
      this.tile.height = h;
    }
    const frame = this.tileContext.createImageData(w, h);
    const source = image?.naturalWidth ? this.pixels(image) : undefined;
    this.cameraToLocal.copy(body.quaternion).invert().multiply(camera.quaternion);
    const c = center.lengthSq() - radius * radius;
    for (let j = 0; j < h; j++) {
      const dy = (height/2 - box.top - (j + 0.5)*box.height/h) / focal;
      for (let i = 0; i < w; i++) {
        const dx = (box.left + (i + 0.5)*box.width/w - width/2) / focal;
        const a = 1 + dx*dx + dy*dy;
        const b = dx*center.x + dy*center.y - center.z;
        const disc = b*b - a*c;
        if (disc < 0) continue;
        const t = (b - Math.sqrt(disc)) / a;
        if (t < camera.near) continue;
        const n = this.normal.set(dx*t-center.x, dy*t-center.y, -t-center.z).multiplyScalar(1/radius);
        const light = Math.sqrt(0.14 + 0.86 * Math.max(0, n.dot(sunCamera)));
        n.applyQuaternion(this.cameraToLocal);
        const src = source ? mapPixel(n.x, n.y, n.z, source.width, source.height) : 0;
        const dst = 4 * (j*w + i);
        for (let k = 0; k < 3; k++) frame.data[dst+k] = (source?.data[src+k] ?? 110) * light;
        frame.data[dst+3] = 255;
      }
    }
    this.tileContext.putImageData(frame, 0, 0);
    ctx.drawImage(this.tile, box.left, box.top, box.width, box.height);
  }
}
